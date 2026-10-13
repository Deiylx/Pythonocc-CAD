# -*- coding: utf-8 -*-
import math
import tempfile
import unittest
from pathlib import Path

from OCC.Core.BRepAdaptor import BRepAdaptor_Curve
from OCC.Core.BRepBuilderAPI import BRepBuilderAPI_MakeEdge
from OCC.Core.BRepPrimAPI import BRepPrimAPI_MakeBox
from OCC.Core.GeomAbs import GeomAbs_Circle
from OCC.Core.gp import gp_Ax2, gp_Circ, gp_Dir, gp_Pnt
from OCC.Core.TopAbs import TopAbs_EDGE
from OCC.Core.TopExp import TopExp_Explorer
from OCC.Core.TopoDS import TopoDS_Shape, topods_Edge

from cad_io.converters.dxf import read_dxf, write_dxf
from cad_io.dxf import DxfWriter
from cad_io.strings import (
    ERR_DXF_EMPTY_SHAPE,
    ERR_DXF_FILE_NOT_FOUND,
    ERR_DXF_NO_SHAPES,
)


def count_edges(shape):
    count = 0
    explorer = TopExp_Explorer(shape, TopAbs_EDGE)
    while explorer.More():
        count += 1
        explorer.Next()
    return count


def polyline_dxf_with_bulge(bulge):
    """Build a minimal DXF R12 file with one bulged polyline segment."""
    return (
        "0\nSECTION\n2\nENTITIES\n"
        "0\nPOLYLINE\n8\n0\n66\n1\n70\n0\n10\n0\n20\n0\n30\n0\n"
        "0\nVERTEX\n8\n0\n10\n0\n20\n0\n42\n{}\n".format(bulge)
        + "0\nVERTEX\n8\n0\n10\n1\n20\n0\n"
        + "0\nSEQEND\n8\n0\n0\nENDSEC\n0\nEOF\n"
    )


class DxfConverterTests(unittest.TestCase):

    def test_box_projects_to_lines_and_imports_as_edges(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "box.dxf"
            shape = BRepPrimAPI_MakeBox(10.0, 20.0, 30.0).Shape()
            write_dxf(shape, str(path))
            content = path.read_text(encoding="utf-8")
            self.assertIn("0\nSECTION\n2\nENTITIES\n", content)
            self.assertEqual(content.count("\nLINE\n"), 8)
            imported = read_dxf(str(path))
            self.assertFalse(imported.IsNull())
            self.assertEqual(count_edges(imported), 8)

    def test_circle_edge_exports_as_circle(self):
        axis = gp_Ax2(
            gp_Pnt(2.0, 3.0, 0.0),
            gp_Dir(0.0, 0.0, 1.0),
        )
        edge = BRepBuilderAPI_MakeEdge(gp_Circ(axis, 4.0)).Edge()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "circle.dxf"
            write_dxf(edge, str(path))
            content = path.read_text(encoding="utf-8")
            self.assertIn("0\nCIRCLE\n", content)
            imported = read_dxf(str(path))
            self.assertEqual(count_edges(imported), 1)

    def test_empty_shape_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "empty.dxf"
            for shape in (None, TopoDS_Shape()):
                with self.assertRaises(ValueError) as ctx:
                    write_dxf(shape, str(path))
                self.assertEqual(str(ctx.exception), ERR_DXF_EMPTY_SHAPE)
            self.assertFalse(path.exists())

    def test_missing_file_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "missing.dxf"
            with self.assertRaises(FileNotFoundError) as ctx:
                read_dxf(str(path))
            self.assertEqual(
                str(ctx.exception),
                ERR_DXF_FILE_NOT_FOUND.format(path=str(path)),
            )

    def test_unsupported_or_empty_file_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "empty.dxf"
            path.write_text(
                "0\nSECTION\n2\nENTITIES\n0\nENDSEC\n0\nEOF\n",
                encoding="utf-8",
            )
            with self.assertRaises(ValueError) as ctx:
                read_dxf(str(path))
            self.assertEqual(
                str(ctx.exception),
                ERR_DXF_NO_SHAPES.format(path=str(path)),
            )

    def test_closed_polyline_imports_as_edges(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "polyline.dxf"
            writer = DxfWriter()
            writer.add_polyline(
                [(0.0, 0.0), (4.0, 0.0), (4.0, 3.0)],
                closed=True,
            )
            writer.save(str(path))
            imported = read_dxf(str(path))
            self.assertEqual(count_edges(imported), 3)

    def test_clockwise_polyline_bulge_imports(self):
        text = polyline_dxf_with_bulge(-0.5)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "clockwise_bulge.dxf"
            path.write_text(text, encoding="utf-8")
            imported = read_dxf(str(path))
            self.assertEqual(count_edges(imported), 1)

    def test_major_polyline_bulges_import_as_major_arcs(self):
        for bulge in (2.0, -2.0):
            with self.subTest(bulge=bulge):
                filename = "major_positive.dxf" if bulge > 0 else "major_negative.dxf"
                with tempfile.TemporaryDirectory() as directory:
                    path = Path(directory) / filename
                    path.write_text(
                        polyline_dxf_with_bulge(bulge),
                        encoding="utf-8",
                    )

                    imported = read_dxf(str(path))
                    self.assertEqual(count_edges(imported), 1)

                    explorer = TopExp_Explorer(imported, TopAbs_EDGE)
                    self.assertTrue(explorer.More())
                    edge = topods_Edge(explorer.Current())
                    curve = BRepAdaptor_Curve(edge)
                    self.assertEqual(curve.GetType(), GeomAbs_Circle)

                    expected_sweep = abs(4.0 * math.atan(bulge))
                    actual_sweep = abs(
                        curve.LastParameter() - curve.FirstParameter()
                    )
                    self.assertAlmostEqual(
                        actual_sweep,
                        expected_sweep,
                        places=6,
                    )

                    expected_radius = 1.0 / (
                        2.0 * math.sin(expected_sweep / 2.0)
                    )
                    self.assertAlmostEqual(
                        curve.Circle().Radius(),
                        expected_radius,
                        places=6,
                    )


if __name__ == "__main__":
    unittest.main()
