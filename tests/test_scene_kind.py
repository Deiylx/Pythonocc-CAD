
"""Тесты выбора 2D- и 3D-геометрии без окон и вьюера."""

import unittest

from OCC.Core.AIS import AIS_ListOfInteractive, AIS_Point, AIS_Shape
from OCC.Core.Bnd import Bnd_Box
from OCC.Core.BRep import BRep_Builder
from OCC.Core.BRepBndLib import brepbndlib_Add
from OCC.Core.BRepBuilderAPI import (
    BRepBuilderAPI_MakeEdge,
    BRepBuilderAPI_MakeVertex,
)
from OCC.Core.BRepPrimAPI import BRepPrimAPI_MakeBox
from OCC.Core.Geom import Geom_CartesianPoint
from OCC.Core.gp import gp_Pnt, gp_Trsf, gp_Vec
from OCC.Core.TopoDS import TopoDS_Compound

from cad_io import scene


def _edge(x1, x2):
    return BRepBuilderAPI_MakeEdge(
        gp_Pnt(x1, 0, 0),
        gp_Pnt(x2, 0, 0),
    ).Edge()


def _compound_of_two_edges():
    """Создать компаунд из двух отдельных рёбер."""
    compound = TopoDS_Compound()
    builder = BRep_Builder()
    builder.MakeCompound(compound)
    builder.Add(compound, _edge(0, 1))
    builder.Add(compound, _edge(2, 3))
    return compound


def _ais_list(*objects):
    ais_list = AIS_ListOfInteractive()
    for obj in objects:
        ais_list.Append(obj)
    return ais_list


def _xmin(shape):
    box = Bnd_Box()
    brepbndlib_Add(shape, box)
    return box.Get()[0]


class ShapesFromAisListKindTest(unittest.TestCase):

    def test_2d_keeps_only_compound_and_edge_in_order(self):
        box = BRepPrimAPI_MakeBox(10, 20, 30).Shape()
        compound = _compound_of_two_edges()
        point = AIS_Point(
            Geom_CartesianPoint(gp_Pnt(5, 5, 5))
        )
        vertex = BRepBuilderAPI_MakeVertex(
            gp_Pnt(6, 0, 0)
        ).Vertex()
        edge = _edge(4, 5)

        ais_list = _ais_list(
            AIS_Shape(box),
            AIS_Shape(compound),
            point,
            AIS_Shape(vertex),
            AIS_Shape(edge),
        )

        shapes = scene.shapes_from_ais_list(
            ais_list, kind="2d"
        )

        self.assertEqual(len(shapes), 2)
        self.assertTrue(shapes[0].IsSame(compound))
        self.assertTrue(shapes[1].IsSame(edge))

    def test_default_and_3d_keep_only_shapes_with_faces(self):
        edge = _edge(0, 1)
        box = BRepPrimAPI_MakeBox(10, 20, 30).Shape()
        ais_list = _ais_list(AIS_Shape(edge), AIS_Shape(box))

        # Старый вызов без аргументов должен работать как прежде.
        default_shapes = scene.shapes_from_ais_list(ais_list)
        self.assertEqual(len(default_shapes), 1)
        self.assertTrue(default_shapes[0].IsSame(box))

        shapes_3d = scene.shapes_from_ais_list(
            ais_list, kind="3d"
        )
        self.assertEqual(len(shapes_3d), 1)
        self.assertTrue(shapes_3d[0].IsSame(box))

    def test_2d_applies_local_transformation(self):
        ais_shape = AIS_Shape(_edge(0, 1))

        transformation = gp_Trsf()
        transformation.SetTranslation(gp_Vec(100, 0, 0))
        ais_shape.SetLocalTransformation(transformation)

        shapes = scene.shapes_from_ais_list(
            _ais_list(ais_shape), kind="2d"
        )

        self.assertEqual(len(shapes), 1)
        self.assertAlmostEqual(_xmin(shapes[0]), 100, places=5)

    def test_invalid_kind_raises_value_error(self):
        ais_list = _ais_list()

        for kind in (None, "3D", "dxf"):
            with self.subTest(kind=kind):
                with self.assertRaises(ValueError):
                    scene.shapes_from_ais_list(
                        ais_list, kind=kind
                    )


class ExportKindAndShapesTest(unittest.TestCase):

    def test_3d_has_priority_over_2d(self):
        edge = _edge(0, 1)
        box = BRepPrimAPI_MakeBox(10, 20, 30).Shape()

        kind, shapes = scene.export_kind_and_shapes(
            _ais_list(AIS_Shape(edge), AIS_Shape(box))
        )

        self.assertEqual(kind, "3d")
        self.assertEqual(len(shapes), 1)
        self.assertTrue(shapes[0].IsSame(box))

    def test_2d_is_selected_when_no_faces_exist(self):
        edge = _edge(0, 1)
        vertex = BRepBuilderAPI_MakeVertex(
            gp_Pnt(2, 0, 0)
        ).Vertex()

        kind, shapes = scene.export_kind_and_shapes(
            _ais_list(AIS_Shape(edge), AIS_Shape(vertex))
        )

        self.assertEqual(kind, "2d")
        self.assertEqual(len(shapes), 1)
        self.assertTrue(shapes[0].IsSame(edge))

    def test_no_exportable_geometry_returns_none_and_empty_list(self):
        point = AIS_Point(
            Geom_CartesianPoint(gp_Pnt(1, 2, 3))
        )
        vertex = BRepBuilderAPI_MakeVertex(
            gp_Pnt(4, 0, 0)
        ).Vertex()

        cases = (
            _ais_list(),
            _ais_list(point),
            _ais_list(AIS_Shape(vertex)),
        )

        for ais_list in cases:
            with self.subTest():
                kind, shapes = scene.export_kind_and_shapes(
                    ais_list
                )
                self.assertIsNone(kind)
                self.assertEqual(shapes, [])
