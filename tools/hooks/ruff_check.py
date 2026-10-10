"""PostToolUse-хук Claude Code: проверка .py-файла ruff после правки.

Запускается системным Python через `py`
(там же ставится ruff: py -m pip install -r tools/requirements.txt).
- cad_io/, tests/, tools/ — полная проверка по ruff.toml;
- остальной старый код — только грубые ошибки (синтаксис, неизвестные имена);
- Win64/python3.7, Sources, Win64/module/Assemble.py (GBK) — пропускаем.
Нашлись ошибки -> код 2, текст в stderr (Claude видит и исправляет).
ruff не установлен -> подсказка и код 0: работа не блокируется.
"""

import importlib.util
import json
import os
import subprocess
import sys

NEW_CODE_DIRS = ("cad_io/", "tests/", "tools/")
SKIP_DIRS = ("win64/python3.7/", "sources/")
SKIP_FILES = ("win64/module/assemble.py",)
LEGACY_RULES = "E9,F63,F7,F82"


def _write_stderr(text):
    sys.stderr.buffer.write((text.rstrip() + "\n").encode("utf-8"))
    sys.stderr.flush()


def relative_path(path, project_dir):
    try:
        rel = os.path.relpath(os.path.abspath(path), os.path.abspath(project_dir))
    except ValueError:  # другой диск в Windows
        return None
    if rel.startswith(".."):
        return None
    return rel.replace("\\", "/")


def main():
    try:
        data = json.loads(sys.stdin.buffer.read().decode("utf-8-sig") or "{}")
    except ValueError:
        return 0
    path = (data.get("tool_input") or {}).get("file_path")
    if not path or not path.lower().endswith(".py"):
        return 0
    project_dir = os.environ.get("CLAUDE_PROJECT_DIR") or data.get("cwd") or os.getcwd()
    rel = relative_path(path, project_dir)
    if rel is None:
        return 0
    key = rel.lower()
    if key in SKIP_FILES or any(key.startswith(d) for d in SKIP_DIRS):
        return 0

    if importlib.util.find_spec("ruff") is None:
        _write_stderr(
            "ruff не установлен в системном Python ({}), проверка пропущена. "
            "Установите: py -m pip install -r tools/requirements.txt".format(sys.executable)
        )
        return 0

    cmd = [sys.executable, "-m", "ruff", "check", "--no-fix", "--force-exclude"]
    if not any(key.startswith(d) for d in NEW_CODE_DIRS):
        cmd += ["--select", LEGACY_RULES]
    cmd.append(rel)
    result = subprocess.run(cmd, cwd=project_dir, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if result.returncode == 0:
        return 0
    output = result.stdout.decode("utf-8", errors="replace")
    _write_stderr("ruff нашёл ошибки в {}:\n{}".format(rel, output))
    return 2


if __name__ == "__main__":
    sys.exit(main())
