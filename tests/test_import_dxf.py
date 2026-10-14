"""Интеграционные тесты импорта DXF через кнопку «导入»."""

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from OCC.Core.BRep import BRep_Builder
from OCC.Core.BRepBuilderAPI import BRepBuilderAPI_MakeEdge
from OCC.Core.TopAbs import TopAbs_EDGE, TopAbs_FACE
from OCC.Core.TopExp import TopExp_Explorer
from OCC.Core.TopoDS import TopoDS_Compound
from OCC.Core.gp import gp_Pnt

from cad_io import strings, ui_bridge
from cad_io.converters.dxf import read_dxf, write_dxf
from cad_io.registry import FormatSpec, Registry


def _two_edge_shape():
    compound = TopoDS_Compound()
    builder = BRep_Builder()
    builder.MakeCompound(compound)
    builder.Add(
        compound,
        BRepBuilderAPI_MakeEdge(gp_Pnt(0, 0, 0), gp_Pnt(10, 0, 0)).Edge(),
    )
    builder.Add(
        compound,
        BRepBuilderAPI_MakeEdge(gp_Pnt(0, 5, 0), gp_Pnt(10, 5, 0)).Edge(),
    )
    return compound


def _count_subshapes(shape, kind):
    count = 0
    explorer = TopExp_Explorer(shape, kind)
    while explorer.More():
        count += 1
        explorer.Next()
    return count


class ImportDxfTest(unittest.TestCase):
    def setUp(self):
        self.registry = Registry()
        self.xyz_shape = object()
        self.xyz_reader = mock.Mock(return_value=self.xyz_shape)
        self.registry.register(FormatSpec("XYZ", (".xyz",), reader=self.xyz_reader))
        self.main_window = mock.Mock()
        self.windows = {}
        self.main_window.Displayshape_core_dict = self.windows
        manager = self.main_window.ModuleWindowManager
        manager.GetWindownName.return_value = ""
        manager.CreatePartWindown.side_effect = self._create_window
        self.actions = ui_bridge.CadIOActions(self.main_window, self.registry)
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        self.directory = Path(temp_dir.name)

    def _window(self, name):
        window = mock.Mock(name=name)
        window.shape_maneger_core_dict = {}
        window.canva._display.DisplayShape.return_value = ["ais_" + name]
        return window

    def _create_window(self, name):
        self.windows[name] = self._window(name)
        self.main_window.ModuleWindowManager.GetWindownName.return_value = name

    def _dxf(self, filename="drawing.dxf"):
        path = self.directory / filename
        write_dxf(_two_edge_shape(), str(path))
        return str(path)

    def _import(self, path):
        with mock.patch.object(ui_bridge, "QFileDialog") as dialog, \
                mock.patch.object(ui_bridge, "QMessageBox") as message_box, \
                mock.patch.object(ui_bridge, "QApplication"):
            dialog.getOpenFileName.return_value = (path, "")
            self.actions.import_file(False)
        return dialog, message_box

    def test_filter_offers_dxf_and_all_supported_patterns_include_it(self):
        dialog, _ = self._import("")
        entries = dialog.getOpenFileName.call_args[0][3].split(";;")
        self.assertIn("DXF (*.dxf)", entries)
        self.assertTrue(entries[0].startswith(strings.ALL_SUPPORTED + " ("))
        self.assertIn("*.dxf", entries[0])

    def test_dxf_from_start_creates_window_and_shows_top_view(self):
        path = self._dxf()
        _, message_box = self._import(path)

        message_box.warning.assert_not_called()
        self.main_window.ModuleWindowManager.CreatePartWindown.assert_called_once_with(
            "drawing"
        )
        display = self.windows["drawing"].canva._display
        display.DisplayShape.assert_called_once()
        shape = display.DisplayShape.call_args[0][0]
        self.assertEqual(_count_subshapes(shape, TopAbs_EDGE), 2)
        self.assertEqual(_count_subshapes(shape, TopAbs_FACE), 0)
        self.assertEqual(
            [call[0] for call in display.method_calls],
            ["DisplayShape", "View_Top", "FitAll"],
        )
        self.main_window.OCAF.Import_part.assert_not_called()
        self.main_window.statusbar.showMessage.assert_called_once_with(
            strings.IMPORT_OK.format(path=path)
        )

    def test_dxf_with_open_detail_uses_a_new_unique_window(self):
        path = self._dxf()
        old_window = self._window("drawing")
        self.windows["drawing"] = old_window
        self.main_window.ModuleWindowManager.GetWindownName.return_value = "drawing"

        self._import(path)

        self.main_window.ModuleWindowManager.CreatePartWindown.assert_called_once_with(
            "drawing (2)"
        )
        old_window.canva._display.DisplayShape.assert_not_called()
        old_window.canva._display.View_Top.assert_not_called()
        self.windows["drawing (2)"].canva._display.View_Top.assert_called_once_with()

    def test_3d_registry_format_stays_in_current_window_without_top_view(self):
        path = self.directory / "model.xyz"
        path.write_text("placeholder")
        current_window = self._window("Part1")
        self.windows["Part1"] = current_window
        self.main_window.ModuleWindowManager.GetWindownName.return_value = "Part1"

        self._import(str(path))

        self.xyz_reader.assert_called_once_with(str(path))
        self.main_window.ModuleWindowManager.CreatePartWindown.assert_not_called()
        current_window.canva._display.View_Top.assert_not_called()
        current_window.canva._display.FitAll.assert_called_once_with()

    def test_broken_dxf_warns_without_creating_a_window(self):
        path = self.directory / "broken.dxf"
        path.write_text("not a DXF file")
        with self.assertRaises(ValueError) as error:
            read_dxf(str(path))

        _, message_box = self._import(str(path))

        message_box.warning.assert_called_once_with(
            self.main_window,
            strings.IMPORT_TITLE,
            strings.IMPORT_FAILED.format(path=str(path), error=error.exception),
        )
        self.main_window.ModuleWindowManager.CreatePartWindown.assert_not_called()
        self.main_window.statusbar.showMessage.assert_not_called()


if __name__ == "__main__":
    unittest.main()
