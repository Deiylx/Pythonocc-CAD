"""Кнопка «导出» (CadIOActions.export_file): в диалоге только 3D-форматы, 2D-формат — отказ.

Окна не открываются: QFileDialog, QMessageBox и сцена окна подменены.
Запуск: .\\Win64\\python3.7\\python.exe -B -m unittest discover -s tests -v
"""

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from cad_io import strings, ui_bridge
from cad_io.registry import FormatSpec, Registry

DXF_FILTER = "DXF (*.dxf)"
STEP_FILTER = "STEP (*.step *.stp)"


class ExportFileKindTest(unittest.TestCase):
    def setUp(self):
        self.reg = Registry()
        self.dxf_writer = mock.Mock(name="write_dxf")
        self.reg.register(FormatSpec("DXF", (".dxf",), writer=self.dxf_writer, kind="2d"))
        self.main_window = mock.Mock()
        self.actions = ui_bridge.CadIOActions(self.main_window, self.reg)
        # Настоящий STEP из register_builtin; запись подменяем, файл не создаётся.
        self.step_writer = mock.Mock(name="write_step")
        self.reg.find_by_extension(".step").writer = self.step_writer
        self.shape = object()
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)

    def _export(self, raw_path, selected_filter):
        """Нажать «导出», будто в диалоге выбраны raw_path и selected_filter.

        Возвращает (подменённый QFileDialog, подменённый QMessageBox).
        """
        with mock.patch.object(ui_bridge, "QFileDialog") as dialog, \
                mock.patch.object(ui_bridge, "QMessageBox") as message_box, \
                mock.patch.object(self.actions, "_current_context", return_value=object()), \
                mock.patch.object(ui_bridge, "displayed_shapes", return_value=[self.shape]), \
                mock.patch.object(ui_bridge, "combine_shapes", return_value=self.shape):
            dialog.getSaveFileName.return_value = (raw_path, selected_filter)
            self.actions.export_file()
        return dialog, message_box

    def test_dialog_offers_only_3d_formats(self):
        dialog, _ = self._export("", "")
        dialog.getSaveFileName.assert_called_once()
        offered = dialog.getSaveFileName.call_args[0][3]
        self.assertEqual(offered, STEP_FILTER)
        self.assertNotIn("DXF", offered)

    def test_2d_format_rejected_with_message(self):
        raw_path = str(self.dir / "part")
        _, message_box = self._export(raw_path, DXF_FILTER)
        self.dxf_writer.assert_not_called()
        self.step_writer.assert_not_called()
        reason = strings.ERR_WRONG_KIND.format(
            name="DXF",
            spec_kind=strings.KIND_LABELS["2d"],
            kind=strings.KIND_LABELS["3d"],
        )
        message_box.warning.assert_called_once_with(
            self.main_window,
            strings.EXPORT_TITLE,
            strings.EXPORT_FAILED.format(path=raw_path, error=reason),
        )
        self.main_window.statusbar.showMessage.assert_not_called()

    def test_3d_format_still_exported(self):
        # Регрессия: STEP сохраняется как раньше.
        _, message_box = self._export(str(self.dir / "part"), STEP_FILTER)
        expected = self.dir / "part.step"
        self.step_writer.assert_called_once_with(self.shape, expected)
        message_box.warning.assert_not_called()
        self.main_window.statusbar.showMessage.assert_called_once_with(
            strings.EXPORT_OK.format(path=expected)
        )


if __name__ == "__main__":
    unittest.main()
