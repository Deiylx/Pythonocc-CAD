import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from OCC.Core.BRepGProp import brepgprop_VolumeProperties
from OCC.Core.BRepPrimAPI import BRepPrimAPI_MakeBox
from OCC.Core.GProp import GProp_GProps
from OCC.Core.TopAbs import TopAbs_FACE, TopAbs_SOLID
from OCC.Core.TopExp import TopExp_Explorer
from OCC.Core.TopoDS import TopoDS_Shape

from cad_io.formats import register_builtin
from cad_io.registry import FormatSpec, Registry
from cad_io.strings import (
    ERR_STEP_EMPTY_SHAPE,
    ERR_STEP_FILE_NOT_FOUND,
    ERR_STEP_NO_SHAPES,
    ERR_STEP_READ_FAILED,
    ERR_STEP_WRITE_FAILED,
)

BOX_VOLUME = 10.0 * 20.0 * 30.0
PROJECT_ROOT = Path(__file__).resolve().parents[1]

# Запись в новом процессе: глобальное состояние OCCT ещё не тронуто другими тестами.
WRITE_IN_FRESH_PROCESS = """
import sys
from OCC.Core.BRepPrimAPI import BRepPrimAPI_MakeBox
from cad_io.formats import register_builtin
from cad_io.registry import Registry
spec = register_builtin(Registry()).find_by_path(sys.argv[1])
spec.writer(BRepPrimAPI_MakeBox(10.0, 20.0, 30.0).Shape(), sys.argv[1])
"""

IMPORT_DOES_NOT_REGISTER = """
import cad_io
import cad_io.formats
assert cad_io.REGISTRY.formats() == [], cad_io.REGISTRY.formats()
"""

# Корректный STEP без единой сущности: ReadFile проходит, переносить нечего.
STEP_WITHOUT_DATA = """ISO-10303-21;
HEADER;
FILE_DESCRIPTION(('empty'),'2;1');
FILE_NAME('empty.step','2026-10-11T00:00:00',(''),(''),'','','');
FILE_SCHEMA(('AUTOMOTIVE_DESIGN { 1 0 10303 214 1 1 1 1 }'));
ENDSEC;
DATA;
ENDSEC;
END-ISO-10303-21;
"""


def make_box():
    return BRepPrimAPI_MakeBox(10.0, 20.0, 30.0).Shape()


def count_subshapes(shape, kind):
    count = 0
    explorer = TopExp_Explorer(shape, kind)
    while explorer.More():
        count += 1
        explorer.Next()
    return count


def count_faces(shape):
    return count_subshapes(shape, TopAbs_FACE)


def count_solids(shape):
    return count_subshapes(shape, TopAbs_SOLID)


def volume(shape):
    props = GProp_GProps()
    brepgprop_VolumeProperties(shape, props)
    return props.Mass()


def run_fresh_python(code, *args):
    """Выполнить код в новом процессе того же Python (PATH к DLL OCC наследуется)."""
    return subprocess.run(
        [sys.executable, "-B", "-c", code] + list(args),
        cwd=str(PROJECT_ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )


class StepRegistrationTests(unittest.TestCase):

    def setUp(self):
        self.reg = register_builtin(Registry())

    def test_extensions_find_step(self):
        for name in ("model.step", "model.STP", "model.stp"):
            spec = self.reg.find_by_path(name)
            self.assertIsNotNone(spec, name)
            self.assertEqual(spec.name, "STEP")

    def test_can_read_and_write(self):
        spec = self.reg.find_by_extension(".step")
        self.assertTrue(spec.can_read)
        self.assertTrue(spec.can_write)
        self.assertEqual(spec.kind, "3d")

    def test_register_builtin_twice(self):
        again = register_builtin(self.reg)
        self.assertIs(again, self.reg)
        names = [spec.name for spec in self.reg.formats()]
        self.assertEqual(names.count("STEP"), 1)

    def test_extension_taken_by_other_format(self):
        reg = Registry()
        reg.register(FormatSpec("OTHER", (".stp",)))
        with self.assertRaises(ValueError):
            register_builtin(reg)

    def test_import_does_not_register(self):
        result = run_fresh_python(IMPORT_DOES_NOT_REGISTER)
        self.assertEqual(
            result.returncode, 0, result.stdout.decode("utf-8", "replace")
        )


class StepRoundtripTests(unittest.TestCase):

    def setUp(self):
        self.reg = register_builtin(Registry())

    def roundtrip(self, path):
        spec = self.reg.find_by_path(str(path))
        box = make_box()
        self.assertEqual(count_faces(box), 6)
        self.assertEqual(count_solids(box), 1)

        spec.writer(box, path)

        self.assertTrue(path.is_file())
        self.assertGreater(path.stat().st_size, 0)

        result = spec.reader(path)

        self.assertFalse(result.IsNull())
        self.assertEqual(count_faces(result), 6)
        self.assertEqual(count_solids(result), 1)
        self.assertAlmostEqual(volume(result), BOX_VOLUME, delta=1e-6 * BOX_VOLUME)

    def test_box_roundtrip(self):
        with tempfile.TemporaryDirectory() as directory:
            self.roundtrip(Path(directory) / "box.step")

    def test_box_roundtrip_cyrillic_path(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory) / "тест_экспорт"
            folder.mkdir()
            self.roundtrip(folder / "деталь.step")

    def test_write_in_fresh_process(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fresh.step"
            result = run_fresh_python(WRITE_IN_FRESH_PROCESS, str(path))
            self.assertEqual(
                result.returncode, 0, result.stdout.decode("utf-8", "replace")
            )
            self.assertTrue(path.is_file())
            self.assertGreater(path.stat().st_size, 0)


class StepErrorTests(unittest.TestCase):

    def setUp(self):
        self.spec = register_builtin(Registry()).find_by_extension(".step")

    def test_write_empty_shape(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "empty.step"
            with self.assertRaises(ValueError) as ctx:
                self.spec.writer(TopoDS_Shape(), path)
            self.assertEqual(str(ctx.exception), ERR_STEP_EMPTY_SHAPE)
            self.assertFalse(path.exists())

    def test_write_none_shape(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "none.step"
            with self.assertRaises(ValueError) as ctx:
                self.spec.writer(None, path)
            self.assertEqual(str(ctx.exception), ERR_STEP_EMPTY_SHAPE)
            self.assertFalse(path.exists())

    def test_write_to_missing_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "нет_папки" / "box.step"
            with self.assertRaises(OSError) as ctx:
                self.spec.writer(make_box(), path)
            self.assertEqual(
                str(ctx.exception),
                ERR_STEP_WRITE_FAILED.format(path=os.fspath(path)),
            )
            self.assertFalse(path.exists())

    def test_read_missing_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "missing.step"
            with self.assertRaises(FileNotFoundError) as ctx:
                self.spec.reader(path)
            self.assertEqual(
                str(ctx.exception),
                ERR_STEP_FILE_NOT_FOUND.format(path=os.fspath(path)),
            )

    def test_read_garbage_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "garbage.step"
            path.write_text("это не STEP\nпросто текст\n", encoding="utf-8")
            with self.assertRaises(ValueError) as ctx:
                self.spec.reader(path)
            self.assertEqual(
                str(ctx.exception),
                ERR_STEP_READ_FAILED.format(path=os.fspath(path)),
            )

    def test_read_empty_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "empty.step"
            path.write_bytes(b"")
            with self.assertRaises(ValueError) as ctx:
                self.spec.reader(path)
            self.assertEqual(
                str(ctx.exception),
                ERR_STEP_READ_FAILED.format(path=os.fspath(path)),
            )

    def test_read_file_without_shapes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "no_data.step"
            path.write_text(STEP_WITHOUT_DATA, encoding="ascii")
            with self.assertRaises(ValueError) as ctx:
                self.spec.reader(path)
            self.assertEqual(
                str(ctx.exception),
                ERR_STEP_NO_SHAPES.format(path=os.fspath(path)),
            )


if __name__ == "__main__":
    unittest.main()
