# -*- coding: utf-8 -*-
import io
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from cad_io.dxf import parse, parse_file
from cad_io.dxf import parser as dxf_parser
from cad_io.dxf.entities import DxfLine, DxfPolyline
from cad_io.strings import (
    DXF_FIELD,
    DXF_FIELD_NAMES,
    ERR_DXF_BAD_NUMBER,
    ERR_DXF_LWPOLYLINE_BULGE_FIRST,
    ERR_DXF_LWPOLYLINE_NO_LAST_Y,
    ERR_DXF_LWPOLYLINE_X_WITHOUT_Y,
    ERR_DXF_LWPOLYLINE_Y_WITHOUT_X,
    ERR_DXF_MISSING_FIELD,
    ERR_DXF_NOT_FINITE,
    ERR_DXF_NOT_INTEGER,
    ERR_DXF_NOT_POSITIVE,
)
import cad_io.strings as dxf_strings


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
        field = DXF_FIELD.format(
            entity="LWPOLYLINE",
            name=DXF_FIELD_NAMES["bulge"],
            code=42,
        )
        with self.assertRaises(ValueError) as ctx:
            parse(text)
        self.assertEqual(
            str(ctx.exception),
            ERR_DXF_NOT_FINITE.format(field=field, value="NaN"),
        )

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

    def test_negative_z_ocs_is_rejected_for_planar_entities(self):
        cases = (
            (
                "ARC",
                "0\nARC\n10\n0\n20\n0\n40\n2\n50\n0\n51\n90\n"
                "210\n0\n220\n0\n230\n-1\n",
            ),
            (
                "CIRCLE",
                "0\nCIRCLE\n10\n0\n20\n0\n40\n2\n"
                "210\n0\n220\n0\n230\n-1\n",
            ),
            (
                "LWPOLYLINE",
                "0\nLWPOLYLINE\n90\n2\n70\n0\n"
                "10\n0\n20\n0\n10\n1\n20\n0\n"
                "210\n0\n220\n0\n230\n-1\n",
            ),
            (
                "POLYLINE",
                "0\nPOLYLINE\n66\n1\n70\n0\n"
                "210\n0\n220\n0\n230\n-1\n"
                "0\nVERTEX\n10\n0\n20\n0\n"
                "0\nVERTEX\n10\n1\n20\n0\n"
                "0\nSEQEND\n",
            ),
        )
        for entity, body in cases:
            with self.subTest(entity=entity):
                with self.assertRaisesRegex(ValueError, "OCS"):
                    parse(_document(body))

    def test_explicit_positive_z_ocs_is_supported(self):
        text = _document(
            "0\nARC\n10\n0\n20\n0\n40\n2\n50\n0\n51\n90\n"
            "210\n0\n220\n0\n230\n1\n"
        )
        self.assertEqual(len(parse(text)), 1)


class DxfParserMessageTests(unittest.TestCase):

    @staticmethod
    def _field(entity, name_key, code):
        return DXF_FIELD.format(
            entity=entity,
            name=DXF_FIELD_NAMES[name_key],
            code=code,
        )

    def test_arc_missing_end_angle_uses_message_template(self):
        text = _document(
            "0\nARC\n10\n0\n20\n0\n40\n2\n50\n0\n"
        )
        with self.assertRaises(ValueError) as ctx:
            parse(text)
        self.assertEqual(
            str(ctx.exception),
            ERR_DXF_MISSING_FIELD.format(
                field=self._field("ARC", "end_angle", 51)
            ),
        )

    def test_arc_bad_end_angle_uses_message_template(self):
        text = _document(
            "0\nARC\n10\n0\n20\n0\n40\n2\n"
            "50\n0\n51\nbad\n"
        )
        with self.assertRaises(ValueError) as ctx:
            parse(text)
        self.assertEqual(
            str(ctx.exception),
            ERR_DXF_BAD_NUMBER.format(
                field=self._field("ARC", "end_angle", 51),
                value="bad",
            ),
        )

    def test_line_infinite_coordinate_uses_message_template(self):
        text = _document(
            "0\nLINE\n10\n0\n20\ninf\n11\n1\n21\n1\n"
        )
        with self.assertRaises(ValueError) as ctx:
            parse(text)
        self.assertEqual(
            str(ctx.exception),
            ERR_DXF_NOT_FINITE.format(
                field=self._field("LINE", "start_y", 20),
                value="inf",
            ),
        )

    def test_lwpolyline_noninteger_flags_use_message_template(self):
        text = _document(
            "0\nLWPOLYLINE\n90\n2\n70\n1.5\n"
            "10\n0\n20\n0\n10\n1\n20\n0\n"
        )
        with self.assertRaises(ValueError) as ctx:
            parse(text)
        self.assertEqual(
            str(ctx.exception),
            ERR_DXF_NOT_INTEGER.format(
                field=self._field("LWPOLYLINE", "flags", 70)
            ),
        )

    def test_circle_and_arc_zero_radius_use_message_template(self):
        cases = (
            (
                "CIRCLE",
                "0\nCIRCLE\n10\n0\n20\n0\n40\n0\n",
            ),
            (
                "ARC",
                "0\nARC\n10\n0\n20\n0\n40\n0\n"
                "50\n0\n51\n90\n",
            ),
        )
        for entity, body in cases:
            with self.subTest(entity=entity):
                with self.assertRaises(ValueError) as ctx:
                    parse(_document(body))
                self.assertEqual(
                    str(ctx.exception),
                    ERR_DXF_NOT_POSITIVE.format(
                        field=self._field(entity, "radius", 40)
                    ),
                )

    def test_lwpolyline_structural_errors_use_message_templates(self):
        cases = (
            (
                "10\n0\n10\n1\n20\n0\n",
                ERR_DXF_LWPOLYLINE_X_WITHOUT_Y,
            ),
            (
                "20\n0\n",
                ERR_DXF_LWPOLYLINE_Y_WITHOUT_X,
            ),
            (
                "42\n0.5\n10\n0\n20\n0\n",
                ERR_DXF_LWPOLYLINE_BULGE_FIRST,
            ),
            (
                "10\n0\n",
                ERR_DXF_LWPOLYLINE_NO_LAST_Y,
            ),
        )
        for fields, expected in cases:
            with self.subTest(fields=fields):
                with self.assertRaises(ValueError) as ctx:
                    parse(_document("0\nLWPOLYLINE\n" + fields))
                self.assertEqual(str(ctx.exception), expected)

    def test_bad_number_constant_can_be_patched_on_parser_module(self):
        text = _document(
            "0\nARC\n10\n0\n20\n0\n40\n2\n"
            "50\n0\n51\nbad\n"
        )
        field = self._field("ARC", "end_angle", 51)
        with mock.patch.object(
            dxf_parser,
            "ERR_DXF_BAD_NUMBER",
            "ПОДМЕНА {field} {value!r}",
        ):
            with self.assertRaises(ValueError) as ctx:
                parse(text)
        self.assertEqual(
            str(ctx.exception),
            "ПОДМЕНА {field} {value!r}".format(
                field=field,
                value="bad",
            ),
        )

    def test_dxf_error_constants_contain_no_english_words(self):
        allowed = {
            "DXF", "LINE", "CIRCLE", "ARC", "LWPOLYLINE", "POLYLINE",
            "VERTEX", "OCS", "X", "Y", "Z",
        }
        values = [DXF_FIELD]
        values.extend(DXF_FIELD_NAMES.values())
        values.extend(
            getattr(dxf_strings, name)
            for name in dir(dxf_strings)
            if name.startswith("ERR_DXF_")
        )
        for value in values:
            without_placeholders = re.sub(r"\{[^{}]*\}", "", value)
            words = re.findall(r"[A-Za-z]+", without_placeholders)
            unexpected = [
                word for word in words if word.upper() not in allowed
            ]
            with self.subTest(value=value):
                self.assertEqual(unexpected, [])


if __name__ == "__main__":
    unittest.main()
