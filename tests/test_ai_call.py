"""Тесты tools/ai_call.py и tools/gemini_review.py — без сети и без google-genai.

Запуск: .\\Win64\\python3.7\\python.exe -B -m unittest discover -s tests -v

tools/ — не пакет, а папка скриптов для системного Python (py). Сами скрипты
делают `import ai_call` (при запуске `py tools/x.py` папка tools/ уже в sys.path),
поэтому тест кладёт tools/ в sys.path так же. google-genai во встроенном 3.7 нет;
ai_call импортирует его только внутри call_gemini(), которую тесты не вызывают.
"""

import io
import json
import os
import ssl
import sys
import tempfile
import unittest
from unittest import mock

TOOLS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools")
if TOOLS_DIR not in sys.path:
    sys.path.insert(0, TOOLS_DIR)

import ai_call  # noqa: E402
import gemini_review  # noqa: E402

FAKE_KEY = "AIzaFAKE-test-key-0123456789"


def _no_network(prompt, model, api_key):
    raise AssertionError("тест не должен отправлять запрос")


class _BinaryStdin(object):
    """Подмена sys.stdin: у настоящего есть .buffer с байтами."""

    def __init__(self, data):
        self.buffer = io.BytesIO(data)


class ResolveModelTest(unittest.TestCase):
    def test_default_model(self):
        self.assertEqual(ai_call.resolve_model(env={}), "gemini-3.8-flash")

    def test_model_from_env(self):
        self.assertEqual(ai_call.resolve_model(env={"GEMINI_MODEL": " m-1 "}), "m-1")

    def test_fast_model_from_env(self):
        env = {"GEMINI_MODEL": "slow", "GEMINI_MODEL_FAST": "quick"}
        self.assertEqual(ai_call.resolve_model(fast=True, env=env), "quick")

    def test_fast_without_env_is_error(self):
        with self.assertRaises(ai_call.AiCallError):
            ai_call.resolve_model(fast=True, env={"GEMINI_MODEL": "slow"})


class ReadPromptTest(unittest.TestCase):
    def test_file_with_bom(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "p.txt")
            with open(path, "wb") as f:
                f.write(b"\xef\xbb\xbf" + "Проверь код 漢字".encode("utf-8"))  # BOM + текст
            self.assertEqual(ai_call.read_prompt(path), "Проверь код 漢字")

    def test_stdin(self):
        stdin = _BinaryStdin("из stdin".encode("utf-8"))
        self.assertEqual(ai_call.read_prompt("-", stdin=stdin), "из stdin")

    def test_empty_rejected(self):
        with self.assertRaises(ai_call.AiCallError):
            ai_call.read_prompt(None, stdin=_BinaryStdin(b"  \n"))

    def test_console_stdin_rejected(self):
        # Без файла и без конвейера скрипт не должен молча ждать ввода.
        stdin = _BinaryStdin(b"")
        stdin.isatty = lambda: True
        with self.assertRaises(ai_call.AiCallError):
            ai_call.read_prompt(None, stdin=stdin)

    def test_too_long_rejected(self):
        data = b"x" * (ai_call.MAX_PROMPT_CHARS + 1)
        with self.assertRaises(ai_call.AiCallError):
            ai_call.read_prompt(None, stdin=_BinaryStdin(data))


class DryRunTest(unittest.TestCase):
    def _run(self, env, prompt="Проверь diff"):
        out, err = io.StringIO(), io.StringIO()
        with tempfile.TemporaryDirectory() as tmp:
            log = os.path.join(tmp, "calls.jsonl")
            code = ai_call.run(prompt, "m-test", dry_run=True, env=env, log_path=log,
                               out=out, err=err, sender=_no_network)
            log_written = os.path.exists(log)
        return code, out.getvalue(), err.getvalue(), log_written

    def test_dry_run_without_key(self):
        code, out, err, log_written = self._run(env={})
        self.assertEqual(code, 0)
        self.assertIn("НЕ отправлен", out)
        self.assertIn("m-test", out)
        self.assertIn("Проверь diff", out)
        self.assertEqual(err, "")
        self.assertFalse(log_written, "dry-run не должен писать журнал")

    def test_dry_run_does_not_print_key(self):
        code, out, err, _ = self._run(env={"GEMINI_API_KEY": FAKE_KEY})
        self.assertEqual(code, 0)
        self.assertNotIn(FAKE_KEY, out + err)

    def test_long_prompt_preview(self):
        text = ai_call.describe_request("m", "a" * 50, preview_chars=10)
        self.assertIn("ещё 40 символов", text)
        self.assertNotIn("a" * 11, text)

    def test_cli_dry_run_without_key(self):
        # main() целиком: аргументы, чтение файла, dry-run. Окружение без ключа.
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "p.txt")
            with open(path, "w", encoding="utf-8") as f:
                f.write("Промпт из файла")
            saved_env, saved_out, saved_err = dict(os.environ), sys.stdout, sys.stderr
            os.environ.pop("GEMINI_API_KEY", None)
            os.environ.pop("GEMINI_MODEL", None)
            # Подменяем оба потока: main() перенастраивает кодировку настоящих.
            sys.stdout, sys.stderr = io.StringIO(), io.StringIO()
            try:
                code = ai_call.main(["--dry-run", path])
                printed = sys.stdout.getvalue()
            finally:
                sys.stdout, sys.stderr = saved_out, saved_err
                os.environ.clear()
                os.environ.update(saved_env)
        self.assertEqual(code, 0)
        self.assertIn("gemini-3.8-flash", printed)
        self.assertIn("Промпт из файла", printed)


class RealCallTest(unittest.TestCase):
    """Реальный путь run() с подменённой отправкой: проверяем журнал и вывод."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.log = os.path.join(self.tmp.name, "logs", "calls.jsonl")

    def tearDown(self):
        self.tmp.cleanup()

    def _run(self, sender, env=None):
        out, err = io.StringIO(), io.StringIO()
        env = {"GEMINI_API_KEY": FAKE_KEY} if env is None else env
        code = ai_call.run("Привет", "m-test", env=env, log_path=self.log,
                           out=out, err=err, sender=sender)
        return code, out.getvalue(), err.getvalue()

    def _log_text(self):
        with open(self.log, "r", encoding="utf-8") as f:
            return f.read()

    def test_missing_key_is_error_without_call(self):
        code, out, err = self._run(_no_network, env={})
        self.assertEqual(code, 2)
        self.assertIn("GEMINI_API_KEY", err)
        self.assertFalse(os.path.exists(self.log))

    def test_success_writes_log_line_without_key(self):
        seen = {}

        def sender(prompt, model, api_key):
            seen["key"] = api_key
            return "ответ модели"

        code, out, err = self._run(sender)
        self.assertEqual(code, 0)
        self.assertEqual(seen["key"], FAKE_KEY)  # ключ передан в отправку...
        self.assertEqual(out, "ответ модели\n")
        text = self._log_text()
        self.assertNotIn(FAKE_KEY, text)  # ...но не в журнал
        lines = text.splitlines()
        self.assertEqual(len(lines), 1)
        record = json.loads(lines[0])
        self.assertEqual(record["model"], "m-test")
        self.assertEqual(record["prompt_chars"], len("Привет"))
        self.assertEqual(record["status"], "ok")
        self.assertEqual(record["response_chars"], len("ответ модели"))
        self.assertIn("time", record)

    def test_log_appends(self):
        self._run(lambda p, m, k: "1")
        self._run(lambda p, m, k: "2")
        self.assertEqual(len(self._log_text().splitlines()), 2)

    def test_key_in_answer_is_redacted(self):
        code, out, err = self._run(lambda p, m, k: "эхо " + k)
        self.assertEqual(code, 0)
        self.assertEqual(out, "эхо ***\n")

    def test_empty_answer_is_not_ok(self):
        code, out, err = self._run(lambda p, m, k: "  ")
        self.assertEqual(code, 1)
        self.assertIn("Пустой ответ", err)
        self.assertEqual(json.loads(self._log_text())["status"], "empty")

    def test_setup_error_is_not_logged(self):
        # Так выглядит отсутствие google-genai: запрос не уходил -> журнал не пишем.
        def sender(prompt, model, api_key):
            raise ai_call.AiCallError("Нет google-genai")

        code, out, err = self._run(sender)
        self.assertEqual(code, 2)
        self.assertIn("google-genai", err)
        self.assertFalse(os.path.exists(self.log))

    def test_error_with_key_in_message_is_redacted(self):
        def sender(prompt, model, api_key):
            raise RuntimeError("400 bad request ?key=" + api_key)

        code, out, err = self._run(sender)
        self.assertEqual(code, 1)
        self.assertNotIn(FAKE_KEY, out + err)
        text = self._log_text()
        self.assertNotIn(FAKE_KEY, text)
        record = json.loads(text)
        self.assertEqual(record["status"], "error")
        self.assertIn("RuntimeError", record["error"])
        self.assertIn("***", record["error"])


# Подделки исключений с теми же именами классов и полями, что в google-genai 2.29.0
# (errors.APIError: .code, .status, str = "<code> <status>. <details>") и httpx 0.28.1
# (ConnectError -> NetworkError -> TransportError). Сами библиотеки в 3.7 не импортируются.
class APIError(Exception):
    def __init__(self, code, status, message):
        self.code, self.status, self.message = code, status, message
        details = {"error": {"code": code, "message": message, "status": status}}
        super(APIError, self).__init__("{} {}. {}".format(code, status, details))


class ClientError(APIError):
    pass


class ServerError(APIError):
    pass


class TransportError(Exception):
    pass


class NetworkError(TransportError):
    pass


class ConnectError(NetworkError):
    pass


class ReadTimeout(TransportError):
    pass


def _unavailable():
    return ServerError(503, "UNAVAILABLE", "This model is currently experiencing high demand.")


def _quota():
    return ClientError(429, "RESOURCE_EXHAUSTED", "You exceeded your current quota.")


def _location():
    return ClientError(400, "FAILED_PRECONDITION",
                       "User location is not supported for the API use.")


class ConnectTimeout(TransportError):
    pass


class RemoteProtocolError(TransportError):
    pass


class IsRetryableTest(unittest.TestCase):
    def test_retryable(self):
        for exc in (_unavailable(), ServerError(500, "INTERNAL", "x"), _location(),
                    ConnectError("EOF occurred in violation of protocol (_ssl.c:997)"),
                    ConnectTimeout("t"), RemoteProtocolError("Server disconnected"),
                    ssl.SSLEOFError(8, "EOF"),  # настоящий класс stdlib
                    ConnectionResetError(10054, "WinError 10054")):
            self.assertTrue(ai_call.is_retryable(exc), repr(exc))

    def test_not_retryable(self):
        for exc in (_quota(), ClientError(400, "INVALID_ARGUMENT", "bad request"),
                    ClientError(404, "NOT_FOUND", "no model"),
                    ClientError(400, "FAILED_PRECONDITION", "billing required"),
                    APIError(None, None, "без кода"),
                    ReadTimeout("timed out"), ValueError("x"), RuntimeError("x")):
            self.assertFalse(ai_call.is_retryable(exc), repr(exc))

    def test_delay_for_every_retry(self):
        # RETRY_DELAYS_S[attempt - 1] не должен выйти за границу, если поменять MAX_ATTEMPTS.
        self.assertEqual(len(ai_call.RETRY_DELAYS_S), ai_call.MAX_ATTEMPTS - 1)


class RetryTest(unittest.TestCase):
    """Повтор в run(): отправка и пауза подменены, сети и настоящих пауз нет."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.log = os.path.join(self.tmp.name, "calls.jsonl")
        self.sleeps = []
        self.calls = 0

    def _run(self, outcomes):
        """outcomes — по одному на попытку: исключение (бросить) или строка (ответ)."""
        def sender(prompt, model, api_key):
            self.calls += 1
            outcome = outcomes[self.calls - 1]
            if isinstance(outcome, Exception):
                raise outcome
            return outcome

        out, err = io.StringIO(), io.StringIO()
        code = ai_call.run("Привет", "m-test", env={"GEMINI_API_KEY": FAKE_KEY},
                           log_path=self.log, out=out, err=err, sender=sender,
                           sleep=self.sleeps.append)
        return code, out.getvalue(), err.getvalue()

    def _records(self):
        with open(self.log, "r", encoding="utf-8") as f:
            text = f.read()
        self.assertNotIn(FAKE_KEY, text)
        return [json.loads(line) for line in text.splitlines()]

    def test_retry_on_503_then_ok(self):
        code, out, err = self._run([_unavailable(), "ответ"])
        self.assertEqual(code, 0)
        self.assertEqual(out, "ответ\n")
        self.assertEqual(self.calls, 2)
        self.assertEqual(self.sleeps, [5])
        self.assertIn("Попытка 1/3", err)
        records = self._records()
        self.assertEqual([(r["attempt"], r["status"]) for r in records], [(1, "error"), (2, "ok")])
        self.assertIn("503 UNAVAILABLE", records[0]["error"])

    def test_retry_on_connect_error_then_ok(self):
        code, out, err = self._run([ConnectError("[WinError 10054] reset"),
                                    ConnectError("EOF occurred in violation of protocol"), "ок"])
        self.assertEqual(code, 0)
        self.assertEqual(self.sleeps, [5, 15])
        self.assertEqual([r["attempt"] for r in self._records()], [1, 2, 3])

    def test_retry_on_location_error(self):
        code, _, _ = self._run([_location(), "ок"])
        self.assertEqual(code, 0)
        self.assertEqual(self.calls, 2)

    def test_empty_after_retry_logs_attempt(self):
        code, _, err = self._run([_unavailable(), "  "])
        self.assertEqual(code, 1)
        self.assertIn("Пустой ответ", err)
        self.assertEqual([(r["attempt"], r["status"]) for r in self._records()],
                         [(1, "error"), (2, "empty")])

    def test_no_retry_on_429(self):
        code, out, err = self._run([_quota(), "не должно дойти"])
        self.assertEqual(code, 1)
        self.assertEqual(self.calls, 1)
        self.assertEqual(self.sleeps, [])
        self.assertIn("429 RESOURCE_EXHAUSTED", err)
        records = self._records()
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["attempt"], 1)

    def test_no_retry_on_other_4xx(self):
        code, _, _ = self._run([ClientError(400, "INVALID_ARGUMENT", "bad"), "не должно дойти"])
        self.assertEqual(code, 1)
        self.assertEqual(self.calls, 1)

    def test_stops_after_three_attempts(self):
        code, out, err = self._run([_unavailable(), _unavailable(), _unavailable(), "лишняя"])
        self.assertEqual(code, 1)
        self.assertEqual(self.calls, 3)
        self.assertEqual(self.sleeps, [5, 15])
        self.assertEqual(out, "")
        self.assertIn("попытка 3/3", err)
        records = self._records()
        self.assertEqual([(r["attempt"], r["status"]) for r in records],
                         [(1, "error"), (2, "error"), (3, "error")])

    def test_key_not_in_log_or_output_on_retries(self):
        def leaky():
            return ConnectError("failed for https://x/?key=" + FAKE_KEY)

        code, out, err = self._run([leaky(), leaky(), leaky()])
        self.assertEqual(code, 1)
        self.assertNotIn(FAKE_KEY, out + err)
        self.assertIn("***", err)
        self.assertEqual(len(self._records()), 3)  # _records() проверяет и отсутствие ключа


class ReviewPromptTest(unittest.TestCase):
    DIFF = "diff --git a/cad_io/x.py b/cad_io/x.py\n+print('hi')\n"
    STATUS = "?? tools/new.py\n"
    AGENTS = "# AGENTS.md\nПравило: Python 3.7\n"

    def test_prompt_contains_all_parts(self):
        prompt = gemini_review.build_review_prompt(self.DIFF, self.STATUS, self.AGENTS)
        self.assertIn("Правило: Python 3.7", prompt)
        self.assertIn("?? tools/new.py", prompt)
        self.assertIn("+print('hi')", prompt)
        self.assertIn("git diff master...HEAD", prompt)
        self.assertIn("файл:строка — проблема — серьёзность", prompt)
        self.assertIn("Не переписывай код", prompt)
        self.assertNotIn("ПОСЛЕДНИЙ раунд", prompt)

    def test_empty_diff_and_status_are_labeled(self):
        prompt = gemini_review.build_review_prompt("", "", self.AGENTS, base="dev")
        self.assertIn("незакоммиченных изменений нет", prompt)
        self.assertIn("относительно dev нет", prompt)

    def test_round_two_includes_previous(self):
        prompt = gemini_review.build_review_prompt(
            self.DIFF, self.STATUS, self.AGENTS, round_no=2,
            previous="cad_io/x.py:1 — print — low")
        self.assertIn("ПОСЛЕДНИЙ раунд", prompt)
        self.assertIn("cad_io/x.py:1 — print — low", prompt)

    def test_round_two_requires_previous(self):
        with self.assertRaises(ValueError):
            gemini_review.build_review_prompt(self.DIFF, self.STATUS, self.AGENTS, round_no=2)

    def test_no_third_round(self):
        with self.assertRaises(ValueError):
            gemini_review.build_review_prompt(self.DIFF, self.STATUS, self.AGENTS,
                                              round_no=3, previous="x")

    def test_long_diff_truncated_with_note(self):
        prompt = gemini_review.build_review_prompt("+" * 100, "", self.AGENTS,
                                                   max_diff_chars=10)
        self.assertIn("diff обрезан: показано 10 из 100", prompt)
        self.assertNotIn("+" * 11, prompt)

    def test_previous_rejected_in_round_one(self):
        with self.assertRaises(ValueError):
            gemini_review.build_review_prompt(self.DIFF, self.STATUS, self.AGENTS,
                                              previous="x")

    def test_cli_rejects_third_round(self):
        saved_err = sys.stderr
        sys.stderr = io.StringIO()
        try:
            with self.assertRaises(SystemExit):
                gemini_review.build_parser().parse_args(["--round", "3"])
        finally:
            sys.stderr = saved_err


class ReviewMainTest(unittest.TestCase):
    """gemini_review.main() целиком: git и отправка подменены, файлы — во временной папке."""

    CONTEXT = ("+new line\n", " M tools/x.py\n", "# AGENTS\n")

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.log = os.path.join(self.tmp.name, "calls.jsonl")
        self.sent = []
        patches = [
            mock.patch.object(gemini_review, "collect_context", lambda base: self.CONTEXT),
            mock.patch.object(ai_call, "call_gemini", self._fake_gemini),
            mock.patch.object(ai_call, "LOG_PATH", self.log),
            mock.patch.dict(os.environ, {"GEMINI_API_KEY": FAKE_KEY}),
            mock.patch.object(sys, "stdout", io.StringIO()),
            mock.patch.object(sys, "stderr", io.StringIO()),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def _fake_gemini(self, prompt, model, api_key):
        self.sent.append(prompt)
        return "tools/x.py:1 — пример — low"

    def _path(self, name):
        return os.path.join(self.tmp.name, name)

    def _read(self, name):
        with open(self._path(name), "r", encoding="utf-8") as f:
            return f.read()

    def test_dry_run_out_saves_full_prompt_without_sending(self):
        code = gemini_review.main(["--dry-run", "--out", self._path("p.txt")])
        self.assertEqual(code, 0)
        self.assertEqual(self.sent, [])
        self.assertIn("+new line", self._read("p.txt"))
        self.assertFalse(os.path.exists(self.log))

    def test_round_one_out_saves_answer_and_logs(self):
        code = gemini_review.main(["--out", self._path("r1.txt")])
        self.assertEqual(code, 0)
        self.assertEqual(len(self.sent), 1)
        self.assertEqual(self._read("r1.txt"), "tools/x.py:1 — пример — low\n")
        with open(self.log, "r", encoding="utf-8") as f:
            record = json.loads(f.read())
        self.assertEqual(record["tool"], "gemini_review")
        self.assertNotIn(FAKE_KEY, sys.stdout.getvalue() + json.dumps(record))

    def test_round_two_reads_previous(self):
        with open(self._path("r1.txt"), "w", encoding="utf-8") as f:
            f.write("tools/x.py:1 — старое замечание — low")
        code = gemini_review.main(["--round", "2", "--previous", self._path("r1.txt")])
        self.assertEqual(code, 0)
        self.assertIn("старое замечание", self.sent[0])
        self.assertIn("ПОСЛЕДНИЙ раунд", self.sent[0])

    def test_previous_with_round_one_is_error(self):
        with open(self._path("r1.txt"), "w", encoding="utf-8") as f:
            f.write("x")
        code = gemini_review.main(["--previous", self._path("r1.txt")])
        self.assertEqual(code, 2)
        self.assertEqual(self.sent, [])

    def test_retry_goes_through_ai_call(self):
        # Первая попытка — 503, вторая — ответ. Пауза подменена: тест не ждёт 5 с.
        answers = [_unavailable(), "tools/x.py:1 — после повтора — low"]

        def flaky(prompt, model, api_key):
            self.sent.append(prompt)
            answer = answers.pop(0)
            if isinstance(answer, Exception):
                raise answer
            return answer

        with mock.patch.object(ai_call, "call_gemini", flaky), \
                mock.patch.object(ai_call.time, "sleep") as fake_sleep:
            code = gemini_review.main(["--out", self._path("r1.txt")])
        self.assertEqual(code, 0)
        self.assertEqual(len(self.sent), 2)
        fake_sleep.assert_called_once_with(5)
        self.assertEqual(self._read("r1.txt"), "tools/x.py:1 — после повтора — low\n")
        with open(self.log, "r", encoding="utf-8") as f:
            records = [json.loads(line) for line in f.read().splitlines()]
        self.assertEqual([(r["tool"], r["attempt"], r["status"]) for r in records],
                         [("gemini_review", 1, "error"), ("gemini_review", 2, "ok")])

    def test_bad_out_path_is_reported(self):
        bad = os.path.join(self.tmp.name, "нет_папки", "r1.txt")
        code = gemini_review.main(["--out", bad])
        self.assertEqual(code, 1)
        self.assertIn("Не удалось записать", sys.stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
