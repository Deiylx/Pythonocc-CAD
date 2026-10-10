"""PreToolUse-хук Claude Code: запрещает правки в защищённых путях.

Запускается системным Python через `py`.
Ловит только встроенные инструменты правки Claude (Edit/Write/...), не запись через терминал.
Читает JSON со stdin, берёт tool_input.file_path (или notebook_path).
Путь защищён -> код выхода 2 и причина в stderr:
Claude Code отменяет правку и показывает причину Claude.
"""

import json
import os
import sys

PROTECTED_DIRS = ("win64/python3.7/", "sources/")
PROTECTED_FILES = ("win64/module/assemble.py",)


def _write_stderr(text):
    sys.stderr.buffer.write((text + "\n").encode("utf-8"))
    sys.stderr.flush()


def relative_key(path, project_dir):
    """Путь относительно корня проекта, в нижнем регистре, с прямыми слэшами."""
    path = os.path.normcase(os.path.abspath(path))
    root = os.path.normcase(os.path.abspath(project_dir))
    try:
        rel = os.path.relpath(path, root)
    except ValueError:  # другой диск в Windows
        return None
    if rel.startswith(".."):
        return None
    return rel.replace("\\", "/").lower()


def is_protected(path, project_dir):
    rel = relative_key(path, project_dir)
    if rel is None:
        return False
    if rel in PROTECTED_FILES:
        return True
    return any(rel.startswith(d) for d in PROTECTED_DIRS)


def main():
    try:
        data = json.loads(sys.stdin.buffer.read().decode("utf-8-sig") or "{}")
    except ValueError:
        return 0
    tool_input = data.get("tool_input") or {}
    path = tool_input.get("file_path") or tool_input.get("notebook_path")
    if not path:
        return 0
    project_dir = os.environ.get("CLAUDE_PROJECT_DIR") or data.get("cwd") or os.getcwd()
    if is_protected(path, project_dir):
        _write_stderr(
            "Запрещено правилами AGENTS.md: {} (Win64/python3.7, Sources и "
            "Win64/module/Assemble.py не меняем).".format(path)
        )
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
