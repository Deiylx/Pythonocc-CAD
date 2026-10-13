# -*- coding: utf-8 -*-
import math
import unittest

from cad_io.dxf.entities import (
    DxfLine,
    DxfPolyline,
    bulge_to_arc,
    fmt_number,
)


class FmtNumberTests(unittest.TestCase):

    def test_integer(self):
        self.assertEqual(fmt_number(5), "5")

    def test_float_no_trailing_zeros(self):
        self.assertEqual(fmt_number(5.5), "5.5")
        self.assertEqual(fmt_number(5.0), "5.0")

    def test_negative_zero_normalized(self):
        self.assertEqual(fmt_number(-0.0), "0.0")

    def test_nan_raises(self):
        with self.assertRaisesRegex(ValueError, "NaN"):
            fmt_number(float("nan"))

    def test_inf_raises(self):
        with self.assertRaisesRegex(ValueError, "Бесконечность"):
            fmt_number(float("inf"))
        with self.assertRaisesRegex(ValueError, "Бесконечность"):
            fmt_number(float("-inf"))


class EntityDefaultsTests(unittest.TestCase):

    def test_line_default_layer(self):
        line = DxfLine((0.0, 0.0), (1.0, 1.0))
        self.assertEqual(line.layer, "0")

    def test_polyline_bulges_default_length(self):
        poly = DxfPolyline([(0, 0), (1, 0), (1, 1)])
        self.assertEqual(len(poly.bulges), 3)
        self.assertEqual(poly.bulges, [0.0, 0.0, 0.0])

    def test_polyline_bulges_padded(self):
        poly = DxfPolyline(
            [(0, 0), (1, 0), (1, 1)],
            bulges=[0.5],
        )
        self.assertEqual(poly.bulges, [0.5, 0.0, 0.0])


class BulgeToArcTests(unittest.TestCase):

    def test_zero_bulge_returns_none(self):
        self.assertIsNone(
            bulge_to_arc((0.0, 0.0), (1.0, 0.0), 0.0)
        )

    def test_zero_chord_returns_none(self):
        self.assertIsNone(
            bulge_to_arc((1.0, 1.0), (1.0, 1.0), 0.5)
        )

    def test_quarter_circle(self):
        bulge = math.tan(math.radians(22.5))
        result = bulge_to_arc((0.0, 0.0), (1.0, 0.0), bulge)

        self.assertIsNotNone(result)

        cx, cy, radius, a1, a2, ccw = result

        self.assertAlmostEqual(
            radius,
            1.0 / (2.0 * math.sin(math.radians(45.0))),
            places=6,
        )
        self.assertTrue(ccw)

    def test_negative_bulge_is_cw(self):
        result = bulge_to_arc((0.0, 0.0), (1.0, 0.0), -0.5)

        self.assertIsNotNone(result)
        self.assertFalse(result[5])

    def test_major_bulges_preserve_sweep(self):
        for bulge in (2.0, -2.0):
            with self.subTest(bulge=bulge):
                result = bulge_to_arc(
                    (0.0, 0.0),
                    (1.0, 0.0),
                    bulge,
                )

                self.assertIsNotNone(result)

                cx, cy, radius, a1, a2, ccw = result

                if ccw:
                    sweep = (a2 - a1) % 360.0
                else:
                    sweep = (a1 - a2) % 360.0

                expected = abs(
                    math.degrees(4.0 * math.atan(bulge))
                )

                self.assertAlmostEqual(
                    sweep,
                    expected,
                    places=6,
                )
                self.assertEqual(ccw, bulge > 0)


if __name__ == "__main__":
    unittest.main()
