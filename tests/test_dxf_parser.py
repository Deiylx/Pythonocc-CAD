# -*- coding: utf-8 -*-
import io
import tempfile
import unittest
from pathlib import Path

from cad_io.dxf import parse, parse_file
from cad_io.dxf.entities import DxfLine, DxfPolyline


def _write(path, text, encoding="utf-8"):
    with io.open(str(path), "w", encoding=encoding, newline="\n") as f:
        f.write(text)


def _document(entity_text):
    return (
        "0\nSECTION\n2\nENTITIES\n"
        + entity_text
        + "0\nENDSEC\n0\nEOF\n"
    )


class DxfParserEdgeCaseTests(unittest.TestCase):

    def test_bom_does_not_break_parser(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bom.dxf"
            text = _document(
                "0\nLINE\n8\n0\n10\n0\n20\n0\n11\n1\n21\n1\n"
            )
            _write(path, text, encoding="utf-8-sig")
            entities = parse_file(str(path))
            self.assertEqual(len(entities), 1)
            self.assertIsInstance(entities[0], DxfLine)

    def test_form_feed_inside_mtext(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ff.dxf"
            text = _document(
                "0\nMTEXT\n8\n0\n1\nfoo\x0cbar\n"
                "0\nLINE\n8\n0\n10\n0\n20\n0\n11\n1\n21\n1\n"
            )
            _write(path, text)
            entities = parse_file(str(path))
            self.assertEqual(len(entities), 1)
            self.assertIsInstance(entities[0], DxfLine)

    def test_garbage_entities_ignored(self):
        text = _document(
            "0\nDIMENSION\n8\n0\n1\nignored\n"
            "0\nHATCH\n8\n0\n1\nignored\n"
            "0\nLINE\n8\n0\n10\n0\n20\n0\n11\n1\n21\n1\n"
        )
        entities = parse(text)
        self.assertEqual(len(entities), 1)
        self.assertIsInstance(entities[0], DxfLine)

    def test_missing_eof_does_not_crash(self):
        text = (
            "0\nSECTION\n2\nENTITIES\n"
            "0\nLINE\n8\n0\n10\n0\n20\n0\n11\n1\n21\n1\n"
        )
        entities = parse(text)
        self.assertEqual(len(entities), 1)

    def test_empty_entities_section(self):
        text = "0\nSECTION\n2\nENTITIES\n0\nENDSEC\n0\nEOF\n"
        self.assertEqual(parse(text), [])

    def test_lwpolyline_with_bulge(self):
        text = _document(
            "0\nLWPOLYLINE\n8\n0\n90\n2\n70\n0\n"
            "10\n0\n20\n0\n42\n0.5\n"
            "10\n10\n20\n0\n"
        )
        entities = parse(text)
        self.assertEqual(len(entities), 1)
        polyline = entities[0]
        self.assertIsInstance(polyline, DxfPolyline)
        self.assertEqual(polyline.points, [(0.0, 0.0), (10.0, 0.0)])
        self.assertEqual(polyline.bulges, [0.5, 0.0])


class DxfParserNumericValidationTests(unittest.TestCase):

    def test_line_requires_all_coordinates(self):
        pairs = [(10, "0"), (20, "0"), (11, "1"), (21, "1")]
        for missing_code in (10, 20, 11, 21):
            with self.subTest(missing_code=missing_code):
                fields = "".join(
                    "{}\n{}\n".format(code, value)
                    for code, value in pairs
                    if code != missing_code
                )
                text = _document("0\nLINE\n" + fields)
                with self.assertRaisesRegex(ValueError, "LINE"):
                    parse(text)

    def test_line_rejects_nonnumeric_and_nonfinite_coordinates(self):
        for bad_value in ("text", "NaN", "inf", "-inf", "1e999"):
            with self.subTest(value=bad_value):
                text = _document(
                    "0\nLINE\n10\n0\n20\n{}\n11\n1\n21\n1\n".format(
                        bad_value
                    )
                )
                with self.assertRaisesRegex(ValueError, "LINE"):
                    parse(text)

    def test_circle_requires_finite_center_coordinates(self):
        for code in (10, 20):
            for bad_value in (None, "NaN", "inf", "not-a-number"):
                with self.subTest(code=code, value=bad_value):
                    fields = {10: "0", 20: "0", 40: "2"}
                    if bad_value is None:
                        del fields[code]
                    else:
                        fields[code] = bad_value
                    body = "".join(
                        "{}\n{}\n".format(field_code, value)
                        for field_code, value in fields.items()
                    )
                    with self.assertRaisesRegex(ValueError, "CIRCLE"):
                        parse(_document("0\nCIRCLE\n" + body))

    def test_circle_requires_positive_finite_radius(self):
        invalid_cases = (
            (None, "missing"),
            ("bad", "nonnumeric"),
            ("NaN", "nan"),
            ("inf", "infinity"),
            ("0", "zero"),
            ("-1", "negative"),
        )
        for radius, label in invalid_cases:
            with self.subTest(radius=radius, label=label):
                fields = "10\n0\n20\n0\n"
                if radius is not None:
                    fields += "40\n{}\n".format(radius)
                with self.assertRaisesRegex(ValueError, "CIRCLE"):
                    parse(_document("0\nCIRCLE\n" + fields))

    def test_arc_requires_finite_angles_and_radius(self):
        for missing_code in (10, 20, 40, 50, 51):
            with self.subTest(missing_code=missing_code):
                fields = {
                    10: "0",
                    20: "0",
                    40: "2",
                    50: "0",
                    51: "90",
                }
                del fields[missing_code]
                body = "".join(
                    "{}\n{}\n".format(field_code, value)
                    for field_code, value in fields.items()
                )
                with self.assertRaisesRegex(ValueError, "ARC"):
                    parse(_document("0\nARC\n" + body))

        for code, bad_value in (
            (10, "NaN"),
            (20, "inf"),
            (40, "-1"),
            (40, "NaN"),
            (40, "0"),
            (50, "NaN"),
            (51, "inf"),
        ):
            with self.subTest(code=code, value=bad_value):
                fields = {
                    10: "0",
                    20: "0",
                    40: "2",
                    50: "0",
                    51: "90",
                }
                fields[code] = bad_value
                body = "".join(
                    "{}\n{}\n".format(field_code, value)
                    for field_code, value in fields.items()
                )
                with self.assertRaisesRegex(ValueError, "ARC"):
                    parse(_document("0\nARC\n" + body))

    def test_lwpolyline_rejects_bad_or_missing_coordinates(self):
        bad_cases = (
            ("10\nNaN\n20\n0\n", "NaN"),
            ("10\n0\n20\ninf\n", "inf"),
            ("10\n0\n", "missing Y"),
            ("20\n0\n", "Y without X"),
        )
        for fields, label in bad_cases:
            with self.subTest(case=label):
                with self.assertRaisesRegex(ValueError, "LWPOLYLINE"):
                    parse(_document("0\nLWPOLYLINE\n" + fields))

    def test_invalid_present_bulge_is_rejected(self):
        text = _document(
            "0\nLWPOLYLINE\n10\n0\n20\n0\n42\nNaN\n"
            "10\n1\n20\n0\n"
        )
        with self.assertRaisesRegex(ValueError, "bulge"):
            parse(text)

    def test_missing_bulge_still_means_straight_segment(self):
        text = _document(
            "0\nLWPOLYLINE\n10\n0\n20\n0\n10\n1\n20\n0\n"
        )
        entities = parse(text)
        self.assertEqual(len(entities), 1)
        self.assertEqual(entities[0].bulges, [0.0, 0.0])

    def test_r12_vertex_requires_finite_coordinates(self):
        text = _document(
            "0\nPOLYLINE\n66\n1\n70\n0\n"
            "0\nVERTEX\n10\nNaN\n20\n0\n"
            "0\nVERTEX\n10\n1\n20\n0\n"
            "0\nSEQEND\n"
        )
        with self.assertRaisesRegex(ValueError, "VERTEX"):
            parse(text)


if __name__ == "__main__":
    unittest.main()
