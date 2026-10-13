# -*- coding: utf-8 -*-
import math
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from OCC.Core.BRep import BRep_Builder
from OCC.Core.BRepAdaptor import BRepAdaptor_Curve
from OCC.Core.BRepBuilderAPI import BRepBuilderAPI_MakeEdge
from OCC.Core.BRepPrimAPI import BRepPrimAPI_MakeBox
from OCC.Core.GeomAbs import GeomAbs_Circle
from OCC.Core.gp import gp_Ax2, gp_Circ, gp_Dir, gp_Pnt
from OCC.Core.TopAbs import TopAbs_EDGE
from OCC.Core.TopExp import TopExp_Explorer
from OCC.Core.TopoDS import TopoDS_Compound, TopoDS_Shape, topods_Edge

from cad_io.converters.dxf import _iter_edges, read_dxf, write_dxf
from cad_io.dxf import DxfWriter
from cad_io.strings import (
    ERR_DXF_EMPTY_SHAPE,
    ERR_DXF_FILE_NOT_FOUND,
    ERR_DXF_NO_SHAPES,
    ERR_DXF_READ_FAILED,
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


def arc_dxf_with_angles(start_angle, end_angle):
    """Build a minimal DXF R12 file containing one ARC entity."""
    return (
        "0\nSECTION\n2\nENTITIES\n"
        "0\nARC\n8\n0\n10\n0\n20\n0\n40\n2\n"
        "50\n{}\n51\n{}\n".format(start_angle, end_angle)
        + "0\nENDSEC\n0\nEOF\n"
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

    def test_read_error_includes_parse_reason(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad_arc.dxf"
            path.write_text(
                "0\nSECTION\n2\nENTITIES\n"
                "0\nARC\n10\n0\n20\n0\n40\n2\n50\n0\n51\nbad\n"
                "0\nENDSEC\n0\nEOF\n",
                encoding="utf-8",
            )
            with self.assertRaises(ValueError) as ctx:
                read_dxf(str(path))
            self.assertIn(str(path), str(ctx.exception))
            self.assertIn("end angle", str(ctx.exception))
            self.assertTrue(
                str(ctx.exception).startswith(
                    ERR_DXF_READ_FAILED.split("{path}")[0]
                )
            )
            self.assertIsInstance(ctx.exception.__cause__, ValueError)

    def test_oserror_from_parser_propagates_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "input.dxf"
            path.write_text("exists", encoding="utf-8")
            with mock.patch(
                "cad_io.converters.dxf.parse_file",
                side_effect=OSError("access denied"),
            ):
                with self.assertRaisesRegex(OSError, "access denied"):
                    read_dxf(str(path))


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

    def test_huge_arc_angle_read_completes_in_child_process(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "huge_angle.dxf"
            path.write_text(
                arc_dxf_with_angles(0.0, -1e300),
                encoding="utf-8",
            )
            child_code = (
                "import sys\n"
                "import math\n"
                "from cad_io.converters.dxf import read_dxf\n"
                "from OCC.Core.BRepAdaptor import BRepAdaptor_Curve\n"
                "from OCC.Core.GeomAbs import GeomAbs_Circle\n"
                "from OCC.Core.TopAbs import TopAbs_EDGE\n"
                "from OCC.Core.TopExp import TopExp_Explorer\n"
                "from OCC.Core.TopoDS import topods_Edge\n"
                "shape = read_dxf(sys.argv[1])\n"
                "explorer = TopExp_Explorer(shape, TopAbs_EDGE)\n"
                "assert explorer.More(), 'ARC did not create an edge'\n"
                "curve = BRepAdaptor_Curve(topods_Edge(explorer.Current()))\n"
                "assert math.isfinite(curve.FirstParameter())\n"
                "assert math.isfinite(curve.LastParameter())\n"
                "assert curve.GetType() == GeomAbs_Circle\n"
            )
            try:
                result = subprocess.run(
                    [sys.executable, "-B", "-c", child_code, str(path)],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    timeout=10,
                )
            except subprocess.TimeoutExpired:
                self.fail("read_dxf hung on ARC with an enormous angle")
            self.assertEqual(
                result.returncode,
                0,
                result.stderr.decode("utf-8", "replace"),
            )

    def test_equal_arc_angles_still_make_full_circles(self):
        for angle in (0.0, 360.0, 90.0):
            with self.subTest(angle=angle):
                with tempfile.TemporaryDirectory() as directory:
                    path = Path(directory) / "full_circle.dxf"
                    path.write_text(
                        arc_dxf_with_angles(angle, angle),
                        encoding="utf-8",
                    )
                    imported = read_dxf(str(path))
                    self.assertEqual(count_edges(imported), 1)
                    explorer = TopExp_Explorer(imported, TopAbs_EDGE)
                    edge = topods_Edge(explorer.Current())
                    curve = BRepAdaptor_Curve(edge)
                    self.assertEqual(curve.GetType(), GeomAbs_Circle)
                    sweep = abs(
                        curve.LastParameter() - curve.FirstParameter()
                    )
                    self.assertAlmostEqual(sweep, 2.0 * math.pi, places=6)

    def test_indexed_edge_map_preserves_unique_box_edge_order(self):
        shape = BRepPrimAPI_MakeBox(10.0, 20.0, 30.0).Shape()
        expected = []
        explorer = TopExp_Explorer(shape, TopAbs_EDGE)
        while explorer.More():
            edge = topods_Edge(explorer.Current())
            if not any(edge.IsSame(previous) for previous in expected):
                expected.append(edge)
            explorer.Next()

        actual = list(_iter_edges(shape))
        self.assertEqual(len(expected), 12)
        self.assertEqual(len(actual), 12)
        for actual_edge, expected_edge in zip(actual, expected):
            self.assertTrue(actual_edge.IsSame(expected_edge))

    def test_large_compound_exports_unique_edges(self):
        edge_count = 2000
        builder = BRep_Builder()
        compound = TopoDS_Compound()
        builder.MakeCompound(compound)
        first_edge = None

        for index in range(edge_count):
            edge = BRepBuilderAPI_MakeEdge(
                gp_Pnt(float(index * 2), 0.0, 0.0),
                gp_Pnt(float(index * 2 + 1), 0.0, 0.0),
            ).Edge()
            builder.Add(compound, edge)
            if first_edge is None:
                first_edge = edge

        # The same topological edge is added again; export must deduplicate it.
        builder.Add(compound, first_edge)

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "many_edges.dxf"
            write_dxf(compound, str(path))
            content = path.read_text(encoding="utf-8")

        self.assertEqual(content.count("\nLINE\n"), edge_count)

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

                    midpoint = curve.Value(
                        (curve.FirstParameter() + curve.LastParameter()) / 2.0
                    )
                    self.assertAlmostEqual(midpoint.X(), 0.5, places=6)
                    self.assertAlmostEqual(
                        midpoint.Y(),
                        -1.0 if bulge > 0 else 1.0,
                        places=6,
                    )


if __name__ == "__main__":
    unittest.main()
