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
        self.assertEqual(ai_call.resolve_model(env={}), "gemini-3.1-pro-preview")

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
        self.assertIn("gemini-3.1-pro-preview", printed)
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

    def test_bad_out_path_is_reported(self):
        bad = os.path.join(self.tmp.name, "нет_папки", "r1.txt")
        code = gemini_review.main(["--out", bad])
        self.assertEqual(code, 1)
        self.assertIn("Не удалось записать", sys.stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
