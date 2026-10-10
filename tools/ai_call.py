"""Один запрос к Gemini: промпт из файла или stdin -> ответ в stdout.

Запускается СИСТЕМНЫМ Python (команда py), не Win64\\python3.7:
google-genai 2.29.0 требует Python >= 3.10. Установка:
    py -m pip install -r tools/requirements.txt

Примеры (PowerShell, из корня проекта):
    py tools/ai_call.py --dry-run prompt.txt     # ничего не отправляет
    py tools/ai_call.py prompt.txt               # реальный вызов
    py tools/ai_call.py --fast prompt.txt        # модель из GEMINI_MODEL_FAST
    git diff | py tools/ai_call.py -              # stdin (см. ниже про PowerShell 5.1)

Передавайте путь к файлу: в PowerShell конвейер в программу перекодируется
($OutputEncoding; в Windows PowerShell 5.1 по умолчанию ASCII) — кириллица молча становится «?».

Переменные окружения:
    GEMINI_API_KEY    — ключ (только отсюда; в код, вывод и журнал не попадает);
    GEMINI_MODEL      — модель, по умолчанию gemini-3.1-pro-preview;
    GEMINI_MODEL_FAST — модель для --fast (значения по умолчанию нет).

Каждый реальный вызов дописывает строку JSON в logs/gemini_calls.jsonl
(время, модель, длина промпта, статус). --dry-run в журнал не пишет.

Модуль импортируется и встроенным Python 3.7 (тесты), поэтому синтаксис 3.7,
а google-genai импортируется только внутри call_gemini().
"""

import argparse
import datetime
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_PATH = os.path.join(ROOT, "logs", "gemini_calls.jsonl")

ENV_KEY = "GEMINI_API_KEY"
ENV_MODEL = "GEMINI_MODEL"
ENV_MODEL_FAST = "GEMINI_MODEL_FAST"
DEFAULT_MODEL = "gemini-3.1-pro-preview"

MAX_PROMPT_CHARS = 500000
TIMEOUT_MS = 300000
PREVIEW_CHARS = 2000


class AiCallError(Exception):
    """Ошибка настройки или ввода: печатаем текст и выходим с кодом 2."""


def resolve_model(fast=False, env=None):
    """Имя модели из окружения. --fast без GEMINI_MODEL_FAST — ошибка, имя не угадываем."""
    env = os.environ if env is None else env
    if fast:
        model = (env.get(ENV_MODEL_FAST) or "").strip()
        if not model:
            raise AiCallError(
                "Для --fast задайте переменную {} (имя быстрой модели).".format(ENV_MODEL_FAST)
            )
        return model
    return (env.get(ENV_MODEL) or "").strip() or DEFAULT_MODEL


def read_prompt(path=None, stdin=None):
    """Текст промпта из файла (UTF-8, BOM допустим) или из stdin, если path пустой или '-'."""
    if path and path != "-":
        with open(path, "rb") as f:
            data = f.read()
    else:
        stdin = sys.stdin if stdin is None else stdin
        if hasattr(stdin, "isatty") and stdin.isatty():
            raise AiCallError("Укажите файл с промптом (stdin — консоль, ввода нет).")
        data = stdin.buffer.read() if hasattr(stdin, "buffer") else stdin.read()
    if isinstance(data, bytes):
        data = data.decode("utf-8-sig")
    if not data.strip():
        raise AiCallError("Пустой промпт.")
    if len(data) > MAX_PROMPT_CHARS:
        raise AiCallError(
            "Промпт слишком длинный: {} символов (предел {}).".format(len(data), MAX_PROMPT_CHARS)
        )
    return data


def redact(text, secret):
    """Заменить ключ на *** (на случай, если он попал в текст исключения)."""
    if not text:
        return text
    if secret:
        text = text.replace(secret, "***")
    return text


def describe_request(model, prompt, preview_chars=PREVIEW_CHARS):
    """Что было бы отправлено (для --dry-run). Ключ сюда не передаётся вообще."""
    lines = [
        "[dry-run] Запрос НЕ отправлен.",
        "[dry-run] Модель: {}".format(model),
        "[dry-run] Длина промпта: {} символов".format(len(prompt)),
    ]
    if preview_chars is None or len(prompt) <= preview_chars:
        lines.append("[dry-run] Промпт:")
        lines.append(prompt)
    else:
        lines.append("[dry-run] Начало промпта (первые {} символов):".format(preview_chars))
        lines.append(prompt[:preview_chars])
        lines.append("[dry-run] ... ещё {} символов".format(len(prompt) - preview_chars))
    return "\n".join(lines)


def make_log_record(model, prompt, status, duration_s=None, response=None, error=None,
                    tool="ai_call", now=None):
    """Строка журнала. Ключа здесь нет и быть не может: его не передают в функцию."""
    now = now or datetime.datetime.now().astimezone()
    record = {
        "time": now.isoformat(timespec="seconds"),
        "tool": tool,
        "model": model,
        "prompt_chars": len(prompt),
        "status": status,
    }
    if duration_s is not None:
        record["duration_s"] = round(duration_s, 2)
    if response is not None:
        record["response_chars"] = len(response)
    if error:
        record["error"] = error
    return record


def append_log(record, path=LOG_PATH):
    folder = os.path.dirname(path)
    if folder and not os.path.isdir(folder):
        os.makedirs(folder)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def call_gemini(prompt, model, api_key, timeout_ms=TIMEOUT_MS):
    """Реальный вызов. API сверено с установленной google-genai 2.29.0:
    genai.Client(api_key=, http_options=types.HttpOptions(timeout= в мс)),
    client.models.generate_content(model=, contents=), ответ .text.
    """
    try:
        from google import genai
        from google.genai import types
    except ImportError as exc:  # запрос не уходил — это ошибка настройки, а не вызова
        raise AiCallError("Нет google-genai в {}. Установите: "
                          "py -m pip install -r tools/requirements.txt".format(sys.executable)
                          ) from exc

    client = genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=timeout_ms))
    response = client.models.generate_content(model=model, contents=prompt)
    return response.text or ""  # None бывает при блокировке фильтром или MAX_TOKENS


def _safe_append_log(record, path, err):
    """Журнал не должен ронять скрипт: ответ уже получен и оплачен."""
    try:
        append_log(record, path)
    except OSError as exc:
        err.write("Не удалось записать журнал {}: {}\n".format(path, exc))


def run(prompt, model, dry_run=False, env=None, log_path=None, out=None, err=None,
        sender=None, tool="ai_call"):
    """Выполнить запрос или dry-run. Возвращает код выхода (0 — успех).

    sender(prompt, model, api_key) -> текст ответа; по умолчанию call_gemini
    (в тестах подменяется, чтобы не ходить в сеть). log_path по умолчанию — LOG_PATH.
    """
    log_path = LOG_PATH if log_path is None else log_path
    env = os.environ if env is None else env
    out = sys.stdout if out is None else out
    err = sys.stderr if err is None else err
    if dry_run:
        out.write(describe_request(model, prompt) + "\n")
        return 0

    api_key = (env.get(ENV_KEY) or "").strip()
    if not api_key:
        err.write("Не задана переменная {}. Запрос не отправлен.\n".format(ENV_KEY))
        return 2

    sender = call_gemini if sender is None else sender
    started = time.time()
    try:
        text = sender(prompt, model, api_key)
    except AiCallError as exc:
        err.write("{}\n".format(exc))
        return 2
    except Exception as exc:  # любая ошибка сети/API идёт в журнал, а не в трассировку
        message = redact("{}: {}".format(type(exc).__name__, exc), api_key)[:500]
        _safe_append_log(make_log_record(model, prompt, "error", time.time() - started,
                                         error=message, tool=tool), log_path, err)
        err.write("Ошибка запроса к {}: {}\n".format(model, message))
        return 1
    duration = time.time() - started
    if not text.strip():
        _safe_append_log(make_log_record(model, prompt, "empty", duration, response=text,
                                         tool=tool), log_path, err)
        err.write("Пустой ответ от {} (фильтр безопасности или лимит токенов?).\n".format(model))
        return 1
    out.write(redact(text, api_key).rstrip("\n") + "\n")
    _safe_append_log(make_log_record(model, prompt, "ok", duration, response=text, tool=tool),
                     log_path, err)
    return 0


def setup_utf8_output():
    """Вывод в UTF-8: в диффах и ответах бывают китайские символы, cp1251 их не печатает."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def build_parser():
    parser = argparse.ArgumentParser(
        description="Один запрос к Gemini (промпт из файла или stdin)."
    )
    parser.add_argument("prompt_file", nargs="?", default="-",
                        help="файл с промптом (UTF-8); '-' или пусто — читать stdin")
    parser.add_argument("--dry-run", action="store_true",
                        help="ничего не отправлять, показать, что было бы отправлено")
    parser.add_argument("--fast", action="store_true",
                        help="модель из {} вместо {}".format(ENV_MODEL_FAST, ENV_MODEL))
    return parser


def main(argv=None):
    setup_utf8_output()
    args = build_parser().parse_args(argv)
    try:
        model = resolve_model(fast=args.fast)
        prompt = read_prompt(args.prompt_file)
    except (AiCallError, OSError, UnicodeDecodeError) as exc:
        sys.stderr.write("{}\n".format(exc))
        return 2
    return run(prompt, model, dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
