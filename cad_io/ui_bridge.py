"""Единственное место пакета cad_io, где есть окна Qt.

Пока только диалоги выбора файла. К кнопкам ленты не подключено:
подключение (строка в RibbonMain.ini) — отдельная итерация по согласованию.

TODO (подключение кнопок): BrepCAD.py запускается из корня репозитория, но перед
подключением проверить, что корень репозитория есть в sys.path при запуске BrepCAD.py
(start.bat -> init.bat), иначе `from cad_io import ...` не сработает. Код старого
приложения в этой итерации не меняем.
"""

from PyQt5.QtWidgets import QFileDialog

from cad_io import strings
from cad_io.registry import REGISTRY


def ask_open_path(parent=None, registry=REGISTRY):
    """Показать диалог «Открыть». Вернёт путь или None, если отменили."""
    path, _ = QFileDialog.getOpenFileName(
        parent, strings.IMPORT_TITLE, "", registry.qt_filter("read")
    )
    return path or None


# TODO: второй результат getSaveFileName (выбранный фильтр) сейчас отбрасывается,
# поэтому имя без расширения даёт путь без расширения. Здесь не исправляем.
# Расширение будет определяться по выбранному фильтру в чистой функции без Qt:
# cad_io/export_paths.py::prepare_export_path (первая микрофича Дмитрия).
def ask_save_path(parent=None, registry=REGISTRY):
    """Показать диалог «Сохранить как». Вернёт путь или None, если отменили."""
    path, _ = QFileDialog.getSaveFileName(
        parent, strings.EXPORT_TITLE, "", registry.qt_filter("write")
    )
    return path or None
