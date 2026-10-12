"""Тесты реестра форматов. OCC и Qt не нужны.

Запуск: .\\Win64\\python3.7\\python.exe -B -m unittest discover -s tests -v
"""

import unittest

from cad_io import strings
from cad_io.registry import FormatSpec, Registry


def _reader(path):
    return path


def _writer(shape, path):
    return None


class FormatSpecTest(unittest.TestCase):
    def test_extensions_lowercased(self):
        spec = FormatSpec("STEP", (".STEP", ".Stp"), reader=_reader)
        self.assertEqual(spec.extensions, (".step", ".stp"))

    def test_extension_without_dot_rejected(self):
        with self.assertRaises(ValueError):
            FormatSpec("STEP", ("step",))

    def test_empty_extensions_rejected(self):
        with self.assertRaises(ValueError):
            FormatSpec("STEP", ())

    def test_bad_kind_rejected(self):
        with self.assertRaises(ValueError):
            FormatSpec("DXF", (".dxf",), kind="2D-ish")

    def test_can_read_write(self):
        spec = FormatSpec("OBJ", (".obj",), reader=_reader)
        self.assertTrue(spec.can_read)
        self.assertFalse(spec.can_write)


class RegistryTest(unittest.TestCase):
    def setUp(self):
        self.reg = Registry()
        self.step = self.reg.register(
            FormatSpec("STEP", (".step", ".stp"), reader=_reader, writer=_writer)
        )
        self.iges = self.reg.register(FormatSpec("IGES", (".iges", ".igs"), reader=_reader))
        self.dxf = self.reg.register(FormatSpec("DXF", (".dxf",), writer=_writer, kind="2d"))

    def test_find_by_path_case_insensitive(self):
        self.assertIs(self.reg.find_by_path(r"C:\models\Part.STP"), self.step)
        self.assertIs(self.reg.find_by_path("part.step"), self.step)

    def test_find_igs(self):
        # В старом фильтре OCAFModule .igs не показывался (BUG-004).
        self.assertIs(self.reg.find_by_path("part.igs"), self.iges)

    def test_find_by_extension_without_dot(self):
        self.assertIs(self.reg.find_by_extension("dxf"), self.dxf)

    def test_unknown_returns_none(self):
        self.assertIsNone(self.reg.find_by_path("part.xyz"))
        self.assertIsNone(self.reg.find_by_path("no_extension"))

    def test_duplicate_extension_rejected(self):
        with self.assertRaises(ValueError):
            self.reg.register(FormatSpec("STEP2", (".stp",), reader=_reader))

    def test_readable_and_writable(self):
        self.assertEqual(self.reg.readable(), [self.step, self.iges])
        self.assertEqual(self.reg.writable(), [self.step, self.dxf])

    def test_qt_filter_read_lists_all_extensions(self):
        self.assertEqual(
            self.reg.qt_filter("read"),
            strings.ALL_SUPPORTED + " (*.step *.stp *.iges *.igs);;"
            "STEP (*.step *.stp);;IGES (*.iges *.igs)",
        )

    def test_qt_filter_single_format_has_no_all_entry(self):
        reg = Registry()
        reg.register(FormatSpec("BREP", (".brep",), writer=_writer))
        self.assertEqual(reg.qt_filter("write"), "BREP (*.brep)")

    def test_qt_filter_bad_mode(self):
        with self.assertRaises(ValueError):
            self.reg.qt_filter("delete")

    def test_filter_entry_lists_all_extensions(self):
        self.assertEqual(self.reg.filter_entry(self.iges), "IGES (*.iges *.igs)")

    def test_qt_filter_built_from_filter_entries(self):
        self.assertEqual(
            self.reg.qt_filter("write").split(";;")[1:],
            [self.reg.filter_entry(self.step), self.reg.filter_entry(self.dxf)],
        )

    def test_find_by_filter(self):
        self.assertIs(self.reg.find_by_filter("STEP (*.step *.stp)"), self.step)
        self.assertIs(self.reg.find_by_filter("DXF (*.dxf)"), self.dxf)

    def test_find_by_filter_unknown_or_all_entry_returns_none(self):
        self.assertIsNone(self.reg.find_by_filter(None))
        self.assertIsNone(self.reg.find_by_filter(""))
        self.assertIsNone(self.reg.find_by_filter("BREP (*.brep)"))
        self.assertIsNone(
            self.reg.find_by_filter(strings.ALL_SUPPORTED + " (*.step *.stp *.dxf)")
        )


if __name__ == "__main__":
    unittest.main()
