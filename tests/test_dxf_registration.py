# -*- coding: utf-8 -*-
import unittest

from cad_io.formats import builtin_specs, register_builtin
from cad_io.registry import Registry


class DxfRegistrationTests(unittest.TestCase):

    def test_dxf_is_builtin_2d_reader_and_writer(self):
        specs = builtin_specs()
        dxf_specs = [spec for spec in specs if spec.name == "DXF"]
        self.assertEqual(len(dxf_specs), 1)
        spec = dxf_specs[0]
        self.assertEqual(spec.extensions, (".dxf",))
        self.assertEqual(spec.kind, "2d")
        self.assertTrue(spec.can_read)
        self.assertTrue(spec.can_write)

    def test_register_builtin_adds_dxf_and_keeps_step(self):
        registry = register_builtin(Registry())
        self.assertEqual(registry.find_by_extension(".dxf").name, "DXF")
        self.assertEqual(registry.find_by_extension(".step").name, "STEP")
        self.assertEqual(registry.find_by_extension(".stp").name, "STEP")
        self.assertIs(register_builtin(registry), registry)
        self.assertEqual([s.name for s in registry.formats()].count("DXF"), 1)
        self.assertEqual([s.name for s in registry.formats()].count("STEP"), 1)


if __name__ == "__main__":
    unittest.main()
