# -*- coding: utf-8 -*-
import tempfile
import unittest
from pathlib import Path

from cad_io.dxf import DxfWriter, parse_file


class DxfWriterDumpsTests(unittest.TestCase):

    def test_empty_file_has_sections(self):
        text = DxfWriter().dumps()
        self.assertIn("0\nSECTION\n2\nHEADER\n", text)
        self.assertIn("0\nSECTION\n2\nENTITIES\n", text)
        self.assertTrue(text.endswith("0\nEOF\n"))

    def test_acad_version_r12(self):
        text = DxfWriter().dumps()
        self.assertIn("9\n$ACADVER\n1\nAC1009\n", text)

    def test_line_format(self):
        w = DxfWriter()
        w.add_line(0.0, 0.0, 10.0, 5.5)
        text = w.dumps()
        self.assertIn("0\nLINE\n", text)
        self.assertIn("8\n0\n", text)
        self.assertIn("11\n10.0\n", text)
        self.assertIn("21\n5.5\n", text)

    def test_circle_and_arc(self):
        w = DxfWriter()
        w.add_circle(1.0, 2.0, 3.0)
        w.add_arc(0.0, 0.0, 1.0, 10.0, 80.0)
        text = w.dumps()
        self.assertIn("CIRCLE", text)
        self.assertIn("ARC", text)
        self.assertIn("50\n10.0\n", text)
        self.assertIn("51\n80.0\n", text)

    def test_polyline_r12_structure(self):
        w = DxfWriter()
        w.add_polyline([(0, 0), (1, 0), (1, 1)])
        text = w.dumps()
        self.assertIn("POLYLINE", text)
        self.assertEqual(text.count("\nVERTEX\n"), 3)
        self.assertIn("SEQEND", text)


class DxfWriterRoundtripTests(unittest.TestCase):

    def test_line_roundtrip(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "line.dxf"
            w = DxfWriter()
            w.add_line(0.0, 0.0, 10.0, 5.5)
            w.save(str(path))

            entities = parse_file(str(path))
            self.assertEqual(len(entities), 1)
            line = entities[0]
            self.assertEqual(line.start, (0.0, 0.0))
            self.assertEqual(line.end, (10.0, 5.5))

    def test_mixed_roundtrip(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "mix.dxf"
            w = DxfWriter()
            w.add_line(0, 0, 1, 1)
            w.add_circle(5, 5, 2)
            w.add_arc(0, 0, 3, 10, 80)
            w.add_polyline([(0, 0), (1, 1), (2, 0)], closed=True)
            w.save(str(path))

            entities = parse_file(str(path))
            types = sorted(type(e).__name__ for e in entities)
            self.assertEqual(
                types,
                ["DxfArc", "DxfCircle", "DxfLine", "DxfPolyline"],
            )

    def test_cyrillic_path(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "деталь_零件.dxf"
            w = DxfWriter()
            w.add_line(0, 0, 1, 1)
            w.save(str(path))
            self.assertTrue(path.is_file())
            self.assertEqual(len(parse_file(str(path))), 1)


if __name__ == "__main__":
    unittest.main()
