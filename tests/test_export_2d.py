"""Тесты выбора 2D/3D и экспорта DXF кнопкой «导出»."""

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from OCC.Core.AIS import AIS_ListOfInteractive, AIS_Point, AIS_Shape
from OCC.Core.Bnd import Bnd_Box
from OCC.Core.BRep import BRep_Builder
from OCC.Core.BRepBndLib import brepbndlib_Add
from OCC.Core.BRepBuilderAPI import BRepBuilderAPI_MakeEdge
from OCC.Core.BRepPrimAPI import BRepPrimAPI_MakeBox
from OCC.Core.Geom import Geom_CartesianPoint
from OCC.Core.TopAbs import TopAbs_EDGE
from OCC.Core.TopExp import TopExp_Explorer
from OCC.Core.TopoDS import TopoDS_Compound
from OCC.Core.gp import gp_Pnt, gp_Trsf, gp_Vec

from cad_io import strings, ui_bridge
from cad_io.converters.dxf import read_dxf, write_dxf
from cad_io.registry import Registry

DXF_FILTER = "DXF (*.dxf)"
STEP_FILTER = "STEP (*.step *.stp)"


def _edge(y):
    return BRepBuilderAPI_MakeEdge(
        gp_Pnt(0, y, 0), gp_Pnt(10, y, 0)
    ).Edge()


def _ais_list(*objects):
    ais_list = AIS_ListOfInteractive()
    for obj in objects:
        ais_list.Append(obj)
    return ais_list


def _count_edges(shape):
    count = 0
    explorer = TopExp_Explorer(shape, TopAbs_EDGE)
    while explorer.More():
        count += 1
        explorer.Next()
    return count


class DisplayedContext(object):
    def __init__(self, *objects):
        self.objects = objects

    def DisplayedObjects(self, ais_list):
        for obj in self.objects:
            ais_list.Append(obj)


class Export2dTest(unittest.TestCase):
    def setUp(self):
        self.registry = Registry()
        self.main_window = mock.Mock()
        self.actions = ui_bridge.CadIOActions(self.main_window, self.registry)
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        self.directory = Path(temp_dir.name)

    def test_save_dialog_without_kind_keeps_general_title(self):
        dont_use_native_dialog = ui_bridge.QFileDialog.DontUseNativeDialog
        with mock.patch.object(ui_bridge, "QFileDialog") as dialog:
            dialog.DontUseNativeDialog = dont_use_native_dialog
            dialog.getSaveFileName.return_value = ("", "")
            self.assertEqual(
                ui_bridge.ask_save_path(registry=self.registry), (None, None)
            )
        self.assertEqual(
            dialog.getSaveFileName.call_args[0][1], strings.EXPORT_TITLE
        )
        self.assertIs(
            dialog.getSaveFileName.call_args[1]["options"],
            dont_use_native_dialog,
        )

    def _export(self, context, raw_path="", selected_filter=""):
        dont_use_native_dialog = ui_bridge.QFileDialog.DontUseNativeDialog
        with mock.patch.object(ui_bridge, "QFileDialog") as dialog, \
                mock.patch.object(ui_bridge, "QMessageBox") as message_box, \
                mock.patch.object(
                    self.actions, "_current_context", return_value=context
                ):
            dialog.DontUseNativeDialog = dont_use_native_dialog
            dialog.getSaveFileName.return_value = (raw_path, selected_filter)
            self.actions.export_file()
        return dialog, message_box

    def test_edge_only_scene_has_2d_title_and_dxf_only_filter(self):
        dialog, message_box = self._export(
            DisplayedContext(AIS_Shape(_edge(0)), AIS_Shape(_edge(5)))
        )
        args = dialog.getSaveFileName.call_args[0]
        self.assertEqual(args[1], strings.EXPORT_TITLE_KIND.format(kind="2D"))
        self.assertEqual(args[3], DXF_FILTER)
        message_box.warning.assert_not_called()

    def test_body_and_edges_have_3d_title_and_no_dxf_filter(self):
        context = DisplayedContext(
            AIS_Shape(_edge(0)),
            AIS_Shape(BRepPrimAPI_MakeBox(10, 10, 10).Shape()),
        )
        dialog, message_box = self._export(context)
        args = dialog.getSaveFileName.call_args[0]
        self.assertEqual(args[1], strings.EXPORT_TITLE_KIND.format(kind="3D"))
        self.assertIn(STEP_FILTER, args[3].split(";;"))
        self.assertNotIn(DXF_FILTER, args[3].split(";;"))
        self.assertNotIn("*.dxf", args[3])
        message_box.warning.assert_not_called()

    def test_extensionless_edge_export_writes_dxf_and_reports_success(self):
        raw_path = str(self.directory / "drawing")
        dialog, message_box = self._export(
            DisplayedContext(AIS_Shape(_edge(0)), AIS_Shape(_edge(5))),
            raw_path,
            DXF_FILTER,
        )
        expected_path = self.directory / "drawing.dxf"
        self.assertTrue(expected_path.is_file())
        self.assertEqual(_count_edges(read_dxf(str(expected_path))), 2)
        message_box.warning.assert_not_called()
        self.main_window.statusbar.showMessage.assert_called_once_with(
            strings.EXPORT_OK.format(path=expected_path)
        )
        self.assertEqual(
            dialog.getSaveFileName.call_args[0][1],
            strings.EXPORT_TITLE_KIND.format(kind="2D"),
        )

    def test_dxf_name_with_extension_exports_without_changing_name(self):
        raw_path = str(self.directory / "drawing.dxf")
        self._export(
            DisplayedContext(AIS_Shape(_edge(0))), raw_path, DXF_FILTER
        )

        expected_path = self.directory / "drawing.dxf"
        self.assertTrue(expected_path.is_file())
        self.assertEqual(_count_edges(read_dxf(str(expected_path))), 1)
        self.main_window.statusbar.showMessage.assert_called_once_with(
            strings.EXPORT_OK.format(path=expected_path)
        )

    def test_transformed_ais_edge_exports_at_transformed_coordinates(self):
        edge = BRepBuilderAPI_MakeEdge(
            gp_Pnt(2, 3, 0), gp_Pnt(12, 3, 0)
        ).Edge()
        ais_edge = AIS_Shape(edge)
        transformation = gp_Trsf()
        transformation.SetTranslation(gp_Vec(100, 20, 0))
        ais_edge.SetLocalTransformation(transformation)

        output_path = str(self.directory / "shifted")
        _, message_box = self._export(
            DisplayedContext(ais_edge), output_path, DXF_FILTER
        )

        exported_shape = read_dxf(str(self.directory / "shifted.dxf"))
        box = Bnd_Box()
        brepbndlib_Add(exported_shape, box)
        xmin, ymin, zmin, xmax, ymax, zmax = box.Get()
        self.assertAlmostEqual(xmin, 102, places=5)
        self.assertAlmostEqual(xmax, 112, places=5)
        self.assertAlmostEqual(ymin, 23, places=5)
        self.assertAlmostEqual(ymax, 23, places=5)
        self.assertAlmostEqual(zmin, 0, places=5)
        self.assertAlmostEqual(zmax, 0, places=5)
        self.assertEqual(_count_edges(exported_shape), 1)
        message_box.warning.assert_not_called()

    def test_x_step_name_with_dxf_filter_is_rejected_without_file(self):
        raw_path = str(self.directory / "x.step")
        dialog, message_box = self._export(
            DisplayedContext(AIS_Shape(_edge(0))), raw_path, DXF_FILTER
        )
        self.assertEqual(dialog.getSaveFileName.call_args[0][3], DXF_FILTER)
        self.assertIs(
            dialog.getSaveFileName.call_args[1]["options"],
            ui_bridge.QFileDialog.DontUseNativeDialog,
        )
        expected_error = strings.ERR_WRONG_KIND.format(
            name="STEP", spec_kind="3D", kind="2D"
        )
        message_box.warning.assert_called_once_with(
            self.main_window,
            strings.EXPORT_TITLE,
            strings.EXPORT_FAILED.format(path=raw_path, error=expected_error),
        )
        self.assertEqual(list(self.directory.iterdir()), [])
        self.main_window.statusbar.showMessage.assert_not_called()

    def test_cancelled_export_is_silent(self):
        dialog, message_box = self._export(
            DisplayedContext(AIS_Shape(_edge(0))), "", ""
        )

        dialog.getSaveFileName.assert_called_once()
        message_box.warning.assert_not_called()
        self.assertEqual(list(self.directory.iterdir()), [])
        self.main_window.statusbar.showMessage.assert_not_called()

    def test_point_only_scene_warns_without_opening_dialog(self):
        point = AIS_Point(Geom_CartesianPoint(gp_Pnt(1, 2, 3)))
        dialog, message_box = self._export(DisplayedContext(point))
        dialog.getSaveFileName.assert_not_called()
        message_box.warning.assert_called_once_with(
            self.main_window, strings.EXPORT_TITLE, strings.NOTHING_TO_EXPORT
        )

    def test_missing_context_warns_without_opening_dialog(self):
        dialog, message_box = self._export(None)
        dialog.getSaveFileName.assert_not_called()
        message_box.warning.assert_called_once_with(
            self.main_window, strings.EXPORT_TITLE, strings.NOTHING_TO_EXPORT
        )

    def test_imported_dxf_geometry_can_be_exported_again(self):
        source_path = self.directory / "source.dxf"
        source_shape = _edge(0)
        # Two independent edges are combined to match a DXF reader result.
        compound = TopoDS_Compound()
        builder = BRep_Builder()
        builder.MakeCompound(compound)
        builder.Add(compound, source_shape)
        builder.Add(compound, _edge(5))
        write_dxf(compound, str(source_path))

        windows = {}
        self.main_window.Displayshape_core_dict = windows
        self.main_window.ModuleWindowManager.GetWindownName.return_value = ""

        def create_window(name):
            window = mock.Mock()
            window.shape_maneger_core_dict = {}
            window.canva._display.DisplayShape.side_effect = (
                lambda shape, update=True: [AIS_Shape(shape)]
            )
            windows[name] = window

        self.main_window.ModuleWindowManager.CreatePartWindown.side_effect = create_window

        with mock.patch.object(ui_bridge, "QFileDialog") as open_dialog, \
                mock.patch.object(ui_bridge, "QMessageBox") as message_box, \
                mock.patch.object(ui_bridge, "QApplication"):
            open_dialog.getOpenFileName.return_value = (str(source_path), "")
            self.actions.import_file(False)
        message_box.warning.assert_not_called()

        ais_shape = windows["source"].shape_maneger_core_dict["source"]
        output_path = str(self.directory / "roundtrip")
        with mock.patch.object(ui_bridge, "QFileDialog") as save_dialog, \
                mock.patch.object(ui_bridge, "QMessageBox") as export_message, \
                mock.patch.object(
                    self.actions,
                    "_current_context",
                    return_value=DisplayedContext(ais_shape),
                ):
            save_dialog.getSaveFileName.return_value = (output_path, DXF_FILTER)
            self.actions.export_file()

        roundtrip_path = self.directory / "roundtrip.dxf"
        self.assertEqual(_count_edges(read_dxf(str(roundtrip_path))), 2)
        export_message.warning.assert_not_called()
        self.main_window.statusbar.showMessage.assert_called_with(
            strings.EXPORT_OK.format(path=roundtrip_path)
        )


if __name__ == "__main__":
    unittest.main()
