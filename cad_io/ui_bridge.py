"""Единственное место пакета cad_io, где есть окна Qt.

Диалоги выбора файла и действия для кнопок ленты (CadIOActions).
Подключение к ленте (по согласованию с человеком, правка Win64/): создать
self.CadIO=ui_bridge.CadIOActions(self) в Ui_MainWindow.__init__ (Win64/module/ShowGui.py)
до init_ribbon() и указать connection=self.parent.CadIO.export_file в RibbonMain.ini.
`from cad_io import ...` работает из приложения: start.bat -> init.bat делает
`cd /d %~dp0` и запускает BrepCAD.py, поэтому корень репозитория — sys.path[0].
"""

from PyQt5.QtWidgets import QFileDialog, QMessageBox

from cad_io import strings
from cad_io.export_paths import choose_export_target
from cad_io.formats import register_builtin
from cad_io.registry import REGISTRY
from cad_io.scene import combine_shapes, displayed_shapes


def ask_open_path(parent=None, registry=REGISTRY):
    """Показать диалог «Открыть». Вернёт путь или None, если отменили."""
    path, _ = QFileDialog.getOpenFileName(
        parent, strings.IMPORT_TITLE, "", registry.qt_filter("read")
    )
    return path or None


def ask_save_path(parent=None, registry=REGISTRY, kind=None):
    """Показать диалог «Сохранить как».

    kind ("3d" или "2d") оставляет в фильтре только форматы этого типа.
    Вернёт (путь, выбранная запись фильтра) или (None, None), если отменили.
    Формат и расширение по этой паре выбирает export_paths.choose_export_target.
    """
    path, selected_filter = QFileDialog.getSaveFileName(
        parent, strings.EXPORT_TITLE, "", registry.qt_filter("write", kind=kind)
    )
    if not path:
        return None, None
    return path, selected_filter


class CadIOActions(object):
    """Действия cad_io для ленты главного окна BrepCAD."""

    def __init__(self, main_window, registry=REGISTRY):
        self.main_window = main_window
        self.registry = register_builtin(registry)

    def _current_context(self):
        """AIS_InteractiveContext текущего окна или None, если окна нет."""
        name = getattr(self.main_window, "current_window_name", None)
        windows = getattr(self.main_window, "Displayshape_core_dict", None) or {}
        if name is None or name not in windows:
            return None
        return windows[name].canva._display.Context

    def _warn(self, text):
        QMessageBox.warning(self.main_window, strings.EXPORT_TITLE, text)

    def export_file(self, checked=False):
        """Кнопка «导出»: сохранить модель текущего окна в формат из реестра.

        checked передаёт сигнал triggered. Исключения наружу не выпускаем:
        необработанное исключение в слоте PyQt5 может закрыть программу.
        """
        try:
            context = self._current_context()
            shapes = displayed_shapes(context) if context is not None else []
        except Exception as error:
            self._warn(strings.EXPORT_SCENE_FAILED.format(error=error))
            return
        if not shapes:
            self._warn(strings.NOTHING_TO_EXPORT)
            return

        raw_path = ""
        try:
            shape = combine_shapes(shapes)
            # Окно детали — 3D-модель: 2D-форматы (DXF) не предлагаем и не принимаем.
            raw_path, selected_filter = ask_save_path(self.main_window, self.registry, kind="3d")
            if raw_path is None:
                return
            spec, path = choose_export_target(
                self.registry, raw_path, selected_filter, kind="3d"
            )
            spec.writer(shape, path)
        except Exception as error:
            self._warn(strings.EXPORT_FAILED.format(path=raw_path, error=error))
            return
        try:
            self.main_window.statusbar.showMessage(strings.EXPORT_OK.format(path=path))
        except Exception:
            # Файл уже записан: без строки состояния обходимся молча.
            pass
