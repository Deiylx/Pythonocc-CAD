"""Тесты маршрута «导入» (cad_io.import_route): старый код или реестр. Без Qt."""

import unittest

from cad_io import strings
from cad_io.formats import register_builtin
from cad_io.import_route import (
    ROUTE_LEGACY,
    ROUTE_REGISTRY,
    base_name,
    build_import_registry,
    choose_import_route,
    unique_name,
)
from cad_io.registry import FormatSpec, Registry


def _reader(path):
    return path


def _writer(shape, path):
    return None


class ImportRouteTest(unittest.TestCase):
    def setUp(self):
        # Настоящий набор встроенных форматов (сейчас STEP) плюс выдуманный 3D-формат XYZ.
        self.reg = register_builtin(Registry())
        self.xyz = self.reg.register(FormatSpec("XYZ", (".xyz",), reader=_reader))

    def _route(self, path, registry=None):
        return choose_import_route(build_import_registry(registry or self.reg), path)

    def test_step_iges_stl_go_to_legacy(self):
        for path in ("a.step", "a.STP", "b.iges", "b.IGS", "c.stl"):
            with self.subTest(path=path):
                self.assertEqual(self._route(path), (ROUTE_LEGACY, None))

    def test_registry_step_does_not_replace_legacy(self):
        # STEP есть в реестре, но старый код сохраняет цвета и дерево: STEP остаётся на нём.
        self.assertIsNotNone(self.reg.find_by_extension(".step"))
        self.assertEqual(self._route("model.step")[0], ROUTE_LEGACY)

    def test_unknown_to_legacy_goes_to_registry(self):
        self.assertEqual(self._route("model.xyz"), (ROUTE_REGISTRY, self.xyz))

    def test_registered_iges_stays_legacy(self):
        reg = Registry()
        reg.register(FormatSpec("IGES", (".iges", ".igs"), reader=_reader))
        self.assertEqual(self._route("a.igs", reg), (ROUTE_LEGACY, None))

    def test_partial_overlap_skips_whole_format(self):
        reg = Registry()
        reg.register(FormatSpec("MIX", (".stl", ".abc"), reader=_reader))
        self.assertEqual(self._route("a.stl", reg), (ROUTE_LEGACY, None))
        with self.assertRaises(ValueError):
            self._route("a.abc", reg)

    def test_2d_and_write_only_formats_are_not_offered(self):
        reg = Registry()
        reg.register(FormatSpec("DXF", (".dxf",), reader=_reader, kind="2d"))
        reg.register(FormatSpec("OUT", (".out",), writer=_writer))
        combined = build_import_registry(reg)
        self.assertIsNone(combined.find_by_extension(".dxf"))
        self.assertIsNone(combined.find_by_extension(".out"))

    def test_unknown_extension_raises_with_message(self):
        with self.assertRaises(ValueError) as ctx:
            self._route("notes.txt")
        self.assertEqual(str(ctx.exception), strings.UNKNOWN_FORMAT.format(ext=".txt"))

    def test_no_extension_raises(self):
        with self.assertRaises(ValueError) as ctx:
            self._route("README")
        self.assertEqual(str(ctx.exception), strings.UNKNOWN_FORMAT.format(ext="README"))

    def test_filter_lists_all_extensions(self):
        offered = build_import_registry(self.reg).qt_filter("read", kind="3d")
        entries = offered.split(";;")
        self.assertTrue(entries[0].startswith(strings.ALL_SUPPORTED + " ("))
        self.assertEqual(
            entries[1:],
            ["STEP (*.step *.stp)", "IGES (*.iges *.igs)", "STL (*.stl)", "XYZ (*.xyz)"],
        )
        for pattern in ("*.step", "*.stp", "*.iges", "*.igs", "*.stl", "*.xyz"):
            self.assertIn(pattern, entries[0])

    def test_source_registry_unchanged(self):
        before = self.reg.formats()
        build_import_registry(self.reg)
        self.assertEqual(self.reg.formats(), before)

    def test_base_name(self):
        self.assertEqual(base_name("C:/models/part.v2.step"), "part.v2")
        self.assertEqual(base_name("part"), "part")

    def test_unique_name(self):
        self.assertEqual(unique_name("part", {}), "part")
        self.assertEqual(unique_name("part", {"part": 1}), "part (2)")
        self.assertEqual(unique_name("part", {"part": 1, "part (2)": 1}), "part (3)")


if __name__ == "__main__":
    unittest.main()
