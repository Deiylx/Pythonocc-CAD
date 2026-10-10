"""Второе мнение от Gemini по изменениям ветки: только замечания, без переписывания кода.

Запускается системным Python (команда py), из корня проекта:
    py tools/gemini_review.py --dry-run                 # показать промпт, ничего не отправлять
    py tools/gemini_review.py --dry-run --out p.txt     # полный промпт в файл
    py tools/gemini_review.py                           # раунд 1
    py tools/gemini_review.py --out review1.txt         # раунд 1, ответ ещё и в файл
    py tools/gemini_review.py --round 2 --previous review1.txt   # раунд 2 (последний)

В промпт идут: git diff <base>...HEAD (только закоммиченное!), git status --short
(видно незакоммиченное и новые файлы) и AGENTS.md. Раундов не больше двух.
Ключ, модель и журнал вызовов — как в tools/ai_call.py.
"""

import argparse
import os
import subprocess
import sys

import ai_call

ROOT = ai_call.ROOT
MAX_ROUNDS = 2
MAX_DIFF_CHARS = 200000

INSTRUCTIONS = """\
Ты — второй ревьюер в проекте BrepCAD (Pythonocc-CAD). Ты ТОЛЬКО читаешь.
Не переписывай код, не предлагай готовые патчи и целые функции, не пересказывай diff.

Правила проекта (AGENTS.md) приведены ниже — проверяй изменения на их нарушение.
Особое внимание:
- функции и классы OCC (у нас pythonocc-core 7.4.0, не новее). Ты не видишь файлы
  библиотеки: если не уверен, что имя есть в 7.4.0, так и напиши «проверить grep'ом
  в OCC/Core», а не утверждай, что функции нет или что она есть;
- совместимость с Python 3.7 там, где код запускает встроенный Python (cad_io/, tests/);
- изменения в запрещённых путях (Win64/python3.7/, Sources/, Win64/module/Assemble.py);
- ключи и секреты в коде, выводе, журналах;
- ошибки логики, необработанные исключения, утечки файлов, тесты без проверок.

Формат ответа — только список, по одной строке на замечание, самое серьёзное сверху:
файл:строка — проблема — серьёзность (high / medium / low)

Строку бери из diff (номер в новой версии файла). Если не можешь указать строку — пиши «файл:?».
Не выдумывай замечаний ради списка. Если замечаний нет — ответь одной строкой: Замечаний нет.
"""

ROUND2_INSTRUCTIONS = """\
Это второй и ПОСЛЕДНИЙ раунд ревью. Ниже — замечания первого раунда.
Для каждого из них ответь строкой «исправлено» / «не исправлено» / «спорно» с пояснением в
пару слов. Новые замечания добавляй только high и medium, в том же формате.
"""


def git_output(args, cwd=ROOT):
    """Вывод git как текст UTF-8. Ошибка git -> RuntimeError с его stderr."""
    result = subprocess.run(
        ["git", "-c", "core.quotepath=false"] + list(args),
        cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        raise RuntimeError("git {}: {}".format(
            " ".join(args), result.stderr.decode("utf-8", errors="replace").strip()))
    return result.stdout.decode("utf-8", errors="replace")


def collect_context(base="master", cwd=ROOT):
    """(diff, status, agents) для промпта."""
    diff = git_output(["diff", "{}...HEAD".format(base)], cwd=cwd)
    status = git_output(["status", "--short"], cwd=cwd)
    with open(os.path.join(cwd, "AGENTS.md"), "r", encoding="utf-8-sig") as f:
        agents = f.read()
    return diff, status, agents


def truncate(text, limit):
    """(текст, обрезан ли). Обрезка явная — ревьюер должен знать, что видит не всё."""
    if len(text) <= limit:
        return text, False
    note = "\n[... diff обрезан: показано {} из {} символов ...]\n".format(limit, len(text))
    return text[:limit] + note, True


def build_review_prompt(diff, status, agents, base="master", round_no=1, previous=None,
                        max_diff_chars=MAX_DIFF_CHARS):
    if round_no not in range(1, MAX_ROUNDS + 1):
        raise ValueError("Раунд ревью должен быть от 1 до {}: {!r}".format(MAX_ROUNDS, round_no))
    if round_no > 1 and not (previous or "").strip():
        raise ValueError("Для раунда {} нужны замечания предыдущего раунда.".format(round_no))
    if round_no == 1 and previous:
        raise ValueError("--previous нужен только для раунда 2.")
    diff_text, _ = truncate(diff, max_diff_chars)
    parts = [INSTRUCTIONS]
    if round_no > 1:
        parts += [ROUND2_INSTRUCTIONS, "=== Замечания раунда {} ===".format(round_no - 1),
                  previous.strip()]
    parts += [
        "=== AGENTS.md (правила проекта) ===", agents.strip(),
        "=== git status --short ===", status.strip() or "(пусто: незакоммиченных изменений нет)",
        "=== git diff {}...HEAD ===".format(base),
        diff_text.strip() or "(пусто: закоммиченных изменений относительно {} нет)".format(base),
    ]
    return "\n\n".join(parts) + "\n"


def build_parser():
    parser = argparse.ArgumentParser(description="Ревью изменений ветки силами Gemini.")
    parser.add_argument("--base", default="master", help="с чем сравнивать (по умолчанию master)")
    parser.add_argument("--round", type=int, choices=range(1, MAX_ROUNDS + 1), default=1,
                        dest="round_no", help="номер раунда: 1 или 2 (больше двух не делаем)")
    parser.add_argument("--previous", help="файл с замечаниями предыдущего раунда (для --round 2)")
    parser.add_argument("--out", help="сохранить ответ в файл (UTF-8); с --dry-run — полный промпт")
    parser.add_argument("--dry-run", action="store_true",
                        help="ничего не отправлять, показать промпт")
    parser.add_argument("--fast", action="store_true", help="быстрая модель (GEMINI_MODEL_FAST)")
    return parser


class _Tee(object):
    """Пишет ответ и в stdout, и в буфер (для --out)."""

    def __init__(self, stream):
        self.stream = stream
        self.chunks = []

    def write(self, text):
        self.chunks.append(text)
        self.stream.write(text)


def main(argv=None):
    ai_call.setup_utf8_output()
    args = build_parser().parse_args(argv)
    try:
        model = ai_call.resolve_model(fast=args.fast)
        previous = None
        if args.previous:
            with open(args.previous, "r", encoding="utf-8-sig") as f:
                previous = f.read()
        diff, status, agents = collect_context(args.base)
        prompt = build_review_prompt(diff, status, agents, base=args.base,
                                     round_no=args.round_no, previous=previous)
    except (ai_call.AiCallError, ValueError, RuntimeError, OSError) as exc:
        sys.stderr.write("{}\n".format(exc))
        return 2
    if len(diff) > MAX_DIFF_CHARS:
        sys.stderr.write("Внимание: diff обрезан до {} символов.\n".format(MAX_DIFF_CHARS))
    if args.dry_run:
        # в dry-run --out сохраняет полный промпт (на экране — только начало)
        if args.out and not _write_text(args.out, prompt):
            return 2
        return ai_call.run(prompt, model, dry_run=True)
    out = _Tee(sys.stdout)
    code = ai_call.run(prompt, model, out=out, tool="gemini_review")
    if code == 0 and args.out and not _write_text(args.out, "".join(out.chunks)):
        return 1
    return code


def _write_text(path, text):
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
    except OSError as exc:
        sys.stderr.write("Не удалось записать {}: {}\n".format(path, exc))
        return False
    return True


if __name__ == "__main__":
    sys.exit(main())
