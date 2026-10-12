"""Тесты cad_io.scene: отбор форм из списка AIS и сборка в одну форму. Без окон и вьюера."""

import unittest

from OCC.Core.AIS import AIS_ListOfInteractive, AIS_Point, AIS_Shape
from OCC.Core.Bnd import Bnd_Box
from OCC.Core.BRepBndLib import brepbndlib_Add
from OCC.Core.BRepBuilderAPI import BRepBuilderAPI_MakeEdge
from OCC.Core.BRepPrimAPI import BRepPrimAPI_MakeBox
from OCC.Core.Geom import Geom_CartesianPoint
from OCC.Core.gp import gp_Pnt, gp_Trsf, gp_Vec
from OCC.Core.TopAbs import TopAbs_COMPOUND, TopAbs_SOLID
from OCC.Core.TopExp import TopExp_Explorer
from OCC.Core.TopoDS import TopoDS_Shape

from cad_io.scene import combine_shapes, shapes_from_ais_list
from cad_io.strings import NOTHING_TO_EXPORT


def _box(x=10.0, y=20.0, z=30.0):
    return BRepPrimAPI_MakeBox(x, y, z).Shape()


def _ais_list(objects):
    ais_list = AIS_ListOfInteractive()
    for obj in objects:
        ais_list.Append(obj)
    return ais_list


def _xmin(shape):
    box = Bnd_Box()
    brepbndlib_Add(shape, box)
    return box.Get()[0]


def _count_solids(shape):
    count = 0
    explorer = TopExp_Explorer(shape, TopAbs_SOLID)
    while explorer.More():
        count += 1
        explorer.Next()
    return count


class ShapesFromAisListTest(unittest.TestCase):
    def test_keeps_only_shapes_with_faces(self):
        box = _box()
        edge = BRepBuilderAPI_MakeEdge(gp_Pnt(0, 0, 0), gp_Pnt(1, 0, 0)).Edge()
        point = AIS_Point(Geom_CartesianPoint(gp_Pnt(1, 2, 3)))
        ais_list = _ais_list([AIS_Shape(box), point, AIS_Shape(edge)])

        shapes = shapes_from_ais_list(ais_list)

        self.assertEqual(len(shapes), 1)
        self.assertTrue(shapes[0].IsSame(box))

    def test_moved_object_exported_at_new_place(self):
        ais_shape = AIS_Shape(_box())
        trsf = gp_Trsf()
        trsf.SetTranslation(gp_Vec(100.0, 0.0, 0.0))
        ais_shape.SetLocalTransformation(trsf)

        shapes = shapes_from_ais_list(_ais_list([ais_shape]))

        self.assertEqual(len(shapes), 1)
        self.assertAlmostEqual(_xmin(shapes[0]), 100.0, places=3)

    def test_not_moved_object_keeps_place(self):
        shapes = shapes_from_ais_list(_ais_list([AIS_Shape(_box())]))
        self.assertAlmostEqual(_xmin(shapes[0]), 0.0, places=3)

    def test_null_shape_skipped(self):
        ais_list = _ais_list([AIS_Shape(TopoDS_Shape())])
        self.assertEqual(shapes_from_ais_list(ais_list), [])

    def test_empty_list(self):
        self.assertEqual(shapes_from_ais_list(AIS_ListOfInteractive()), [])


class CombineShapesTest(unittest.TestCase):
    def test_single_shape_returned_as_is(self):
        box = _box()
        self.assertTrue(combine_shapes([box]).IsSame(box))

    def test_two_boxes_make_compound_with_two_solids(self):
        result = combine_shapes([_box(), _box(5.0, 5.0, 5.0)])
        self.assertEqual(result.ShapeType(), TopAbs_COMPOUND)
        self.assertEqual(_count_solids(result), 2)

    def test_empty_list_raises_nothing_to_export(self):
        with self.assertRaises(ValueError) as ctx:
            combine_shapes([])
        self.assertEqual(str(ctx.exception), NOTHING_TO_EXPORT)


if __name__ == "__main__":
    unittest.main()
