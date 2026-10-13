"""Кнопка «导入» (CadIOActions.import_file): маршрут, окно детали, отмена и ошибки.

Окна не открываются: QFileDialog, QMessageBox, QApplication и главное окно подменены.
Запуск: .\\Win64\\python3.7\\python.exe -B -m unittest discover -s tests -v
"""

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from cad_io import strings, ui_bridge
from cad_io.registry import FormatSpec, Registry
from Win64.module import OCAFModule


class ImportFileTest(unittest.TestCase):
    def setUp(self):
        self.reg = Registry()
        self.shape = object()
        self.xyz_reader = mock.Mock(name="read_xyz", return_value=self.shape)
        self.reg.register(FormatSpec("XYZ", (".xyz",), reader=self.xyz_reader))
        self.main_window = mock.Mock()
        self.windows = {}
        self.main_window.Displayshape_core_dict = self.windows
        manager = self.main_window.ModuleWindowManager
        manager.GetWindownName.return_value = ""  # вкладок нет: стартовое окно
        manager.CreatePartWindown.side_effect = self._create_window
        # CadIOActions регистрирует встроенные форматы (STEP) в self.reg.
        self.actions = ui_bridge.CadIOActions(self.main_window, self.reg)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)

    def _window(self, name):
        window = mock.Mock(name=name)
        window.shape_maneger_core_dict = {}
        window.canva._display.DisplayShape.return_value = ["ais_" + name]
        return window

    def _create_window(self, name):
        self.windows[name] = self._window(name)
        self.main_window.ModuleWindowManager.GetWindownName.return_value = name

    def _open_window(self, name="Part1"):
        self.windows[name] = self._window(name)
        self.main_window.ModuleWindowManager.GetWindownName.return_value = name
        return self.windows[name]

    def _file(self, filename):
        path = self.dir / filename
        path.write_text("x")
        return str(path)

    def _import(self, chosen_path):
        """Нажать «导入», будто в диалоге выбран chosen_path.

        Возвращает (подменённый QFileDialog, QMessageBox, QApplication).
        """
        with mock.patch.object(ui_bridge, "QFileDialog") as dialog, \
                mock.patch.object(ui_bridge, "QMessageBox") as message_box, \
                mock.patch.object(ui_bridge, "QApplication") as app:
            dialog.getOpenFileName.return_value = (chosen_path, "")
            self.actions.import_file(False)
        return dialog, message_box, app

    def _assert_no_window_and_no_import(self):
        self.main_window.ModuleWindowManager.CreatePartWindown.assert_not_called()
        self.main_window.OCAF.Import_part.assert_not_called()
        self.xyz_reader.assert_not_called()

    def _warning_text(self, message_box):
        message_box.warning.assert_called_once()
        args = message_box.warning.call_args[0]
        self.assertIs(args[0], self.main_window)
        self.assertEqual(args[1], strings.IMPORT_TITLE)
        return args[2]

    def test_dialog_offers_legacy_and_registry_formats(self):
        dialog, _, _ = self._import("")
        offered = dialog.getOpenFileName.call_args[0][3]
        for entry in ("STEP (*.step *.stp)", "IGES (*.iges *.igs)", "STL (*.stl)",
                      "XYZ (*.xyz)"):
            self.assertIn(entry, offered.split(";;"))

    def test_cancel_is_silent(self):
        _, message_box, _ = self._import("")
        message_box.warning.assert_not_called()
        self._assert_no_window_and_no_import()
        self.main_window.statusbar.showMessage.assert_not_called()

    def test_unknown_extension_warns(self):
        _, message_box, _ = self._import(self._file("notes.txt"))
        self.assertEqual(
            self._warning_text(message_box), strings.UNKNOWN_FORMAT.format(ext=".txt")
        )
        self._assert_no_window_and_no_import()

    def test_missing_file_warns_without_window(self):
        missing = str(self.dir / "no_such.step")
        _, message_box, _ = self._import(missing)
        self.assertEqual(
            self._warning_text(message_box),
            strings.ERR_IMPORT_FILE_NOT_FOUND.format(path=missing),
        )
        self._assert_no_window_and_no_import()

    def test_legacy_format_into_open_window(self):
        self._open_window("Part1")
        for filename in ("model.step", "model.igs", "model.stl"):
            with self.subTest(filename=filename):
                self.main_window.OCAF.Import_part.reset_mock()
                path = self._file(filename)
                _, message_box, _ = self._import(path)
                message_box.warning.assert_not_called()
                self.main_window.OCAF.Import_part.assert_called_once_with(path)
        self.main_window.ModuleWindowManager.CreatePartWindown.assert_not_called()

    def test_legacy_format_without_window_creates_one_first(self):
        # BUG-013: со стартового окна вкладок нет — окно создаётся до старого импорта.
        path = self._file("model.step")
        _, message_box, _ = self._import(path)
        message_box.warning.assert_not_called()
        calls = [c for c in self.main_window.mock_calls
                 if c[0] in ("ModuleWindowManager.CreatePartWindown", "OCAF.Import_part")]
        self.assertEqual(calls, [
            mock.call.ModuleWindowManager.CreatePartWindown("model"),
            mock.call.OCAF.Import_part(path),
        ])

    def test_legacy_import_reads_into_created_window(self):
        # Связка BUG-013 с настоящим OCAF.Import_part: после CreatePartWindown он берёт
        # имя новой вкладки через tabText(currentIndex()) и показывает модель в ней.
        self.main_window.OCAF = OCAFModule.OCAF(parent=self.main_window)
        self.main_window.modeltree_dict = {}
        tabwidget = self.main_window.ModuleWindowManager.tabwidget
        tabwidget.tabText.return_value = ""

        def create_window(name):
            self._create_window(name)
            self.main_window.modeltree_dict[name] = mock.Mock()
            tabwidget.tabText.return_value = name  # CreatePartWindown делает вкладку текущей

        self.main_window.ModuleWindowManager.CreatePartWindown.side_effect = create_window
        path = self._file("model.stl")
        with mock.patch.object(OCAFModule, "QFileDialog") as legacy_dialog, \
                mock.patch.object(OCAFModule, "ProcessWidgets"), \
                mock.patch.object(OCAFModule, "QApplication"), \
                mock.patch.object(OCAFModule, "NoDumpProcess"), \
                mock.patch.object(OCAFModule, "read_stl_file") as read_stl:
            _, message_box, _ = self._import(path)
        message_box.warning.assert_not_called()
        legacy_dialog.getOpenFileName.assert_not_called()
        read_stl.assert_called_once_with(path)
        display = self.windows["model"].canva._display
        display.DisplayShape.assert_called_once_with(read_stl.return_value)

    def test_new_window_name_is_unique(self):
        # Страховка: имя «model» уже занято в словаре окон, а текущей вкладки детали нет.
        # В приложении сейчас так не бывает (обработчика закрытия вкладок нет), но запись
        # окна затирать нельзя.
        self.windows["model"] = self._window("model")
        self._import(self._file("model.stl"))
        self.main_window.ModuleWindowManager.CreatePartWindown.assert_called_once_with(
            "model (2)"
        )

    def test_registry_format_without_window(self):
        path = self._file("model.xyz")
        _, message_box, app = self._import(path)
        message_box.warning.assert_not_called()
        self.xyz_reader.assert_called_once_with(path)
        app.restoreOverrideCursor.assert_called_once_with()
        self.main_window.ModuleWindowManager.CreatePartWindown.assert_called_once_with("model")
        window = self.windows["model"]
        window.canva._display.DisplayShape.assert_called_once_with(self.shape, update=True)
        window.canva._display.FitAll.assert_called_once_with()
        self.assertEqual(window.shape_maneger_core_dict, {"model": "ais_model"})
        self.main_window.InteractiveOperate.Setting.assert_called_once_with()
        self.main_window.OCAF.Import_part.assert_not_called()
        self.main_window.statusbar.showMessage.assert_called_once_with(
            strings.IMPORT_OK.format(path=path)
        )

    def test_registry_format_into_open_window(self):
        window = self._open_window("Part1")
        window.shape_maneger_core_dict["model"] = "old"
        self._import(self._file("model.xyz"))
        self.main_window.ModuleWindowManager.CreatePartWindown.assert_not_called()
        window.canva._display.DisplayShape.assert_called_once_with(self.shape, update=True)
        self.assertEqual(window.shape_maneger_core_dict["model (2)"], "ais_Part1")
        self.assertEqual(window.shape_maneger_core_dict["model"], "old")

    def test_registry_read_error_warns_without_window(self):
        self.xyz_reader.side_effect = ValueError("broken file")
        path = self._file("model.xyz")
        _, message_box, app = self._import(path)
        self.assertEqual(
            self._warning_text(message_box),
            strings.IMPORT_FAILED.format(path=path, error="broken file"),
        )
        app.restoreOverrideCursor.assert_called_once_with()
        self.main_window.ModuleWindowManager.CreatePartWindown.assert_not_called()
        self.main_window.statusbar.showMessage.assert_not_called()

    def test_window_error_warns_instead_of_raising(self):
        self.main_window.ModuleWindowManager.CreatePartWindown.side_effect = RuntimeError("tab")
        path = self._file("model.step")
        _, message_box, _ = self._import(path)
        self.assertEqual(
            self._warning_text(message_box),
            strings.IMPORT_FAILED.format(path=path, error="tab"),
        )
        self.main_window.OCAF.Import_part.assert_not_called()


if __name__ == "__main__":
    unittest.main()
