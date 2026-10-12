"""Кнопка «导入» (OCAF.Import_part): отмена диалога не роняет приложение.

Окна не открываются: диалог выбора файла, окно прогресса и QApplication подменены.
Запуск: .\\Win64\\python3.7\\python.exe -B -m unittest discover -s tests -v
"""

import contextlib
import io
import os
import shutil
import tempfile
import unittest
from unittest import mock

from Win64.module import OCAFModule


class ImportPartCancelTest(unittest.TestCase):
    def setUp(self):
        self.parent = mock.Mock()
        self.parent.ModuleWindowManager.tabwidget.currentIndex.return_value = 0
        self.parent.ModuleWindowManager.tabwidget.tabText.return_value = "Part1"
        self.ocaf = OCAFModule.OCAF(parent=self.parent)

    def _run_import(self, chosen_path):
        """Вызвать Import_part, будто в диалоге выбран chosen_path.

        Возвращает (подменённый ProcessWidgets, напечатанное в stdout).
        """
        out = io.StringIO()
        with mock.patch.object(OCAFModule, "QFileDialog") as dialog, \
                mock.patch.object(OCAFModule, "ProcessWidgets") as widgets, \
                mock.patch.object(OCAFModule, "QApplication"), \
                contextlib.redirect_stdout(out):
            dialog.getOpenFileName.return_value = (chosen_path, "")
            self.ocaf.Import_part()
        return widgets, out.getvalue()

    def test_cancel_is_silent(self):
        widgets, printed = self._run_import("")
        widgets.ProcessWidget.assert_not_called()
        self.parent.statusbar.showMessage.assert_not_called()
        self.assertEqual(printed, "")

    def _tmp_path(self, filename, create):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp)
        path = os.path.join(tmp, filename)
        if create:
            with open(path, "w") as f:
                f.write("x")
        return path

    def test_missing_file_is_silent(self):
        missing = self._tmp_path("no_such_file.stp", create=False)
        widgets, printed = self._run_import(missing)
        widgets.ProcessWidget.assert_not_called()
        self.parent.statusbar.showMessage.assert_not_called()
        self.assertEqual(printed, "")

    def test_progress_closed_when_file_chosen(self):
        # Файл существует, но формат не распознан: ни одна ветка чтения не выполняется,
        # а окно прогресса должно открыться и закрыться.
        path = self._tmp_path("model.txt", create=True)
        widgets, _ = self._run_import(path)
        progress = widgets.ProcessWidget.return_value
        widgets.ProcessWidget.assert_called_once_with(self.parent)
        progress.Show.assert_called_once_with()
        progress.Close.assert_called_once_with()

    def test_progress_closed_once_when_reader_fails(self):
        # Окно прогресса создано, затем чтение STL падает: Import_part печатает ошибку
        # (так было и до исправления), а окно закрывается ровно один раз.
        path = self._tmp_path("model.stl", create=True)
        with mock.patch.object(OCAFModule, "read_stl_file",
                               side_effect=RuntimeError("stl read failed")):
            widgets, printed = self._run_import(path)
        progress = widgets.ProcessWidget.return_value
        widgets.ProcessWidget.assert_called_once_with(self.parent)
        progress.Close.assert_called_once_with()
        self.assertIn("stl read failed", printed)


if __name__ == "__main__":
    unittest.main()
