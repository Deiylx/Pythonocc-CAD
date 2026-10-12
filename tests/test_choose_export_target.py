"""Тесты choose_export_target: формат и путь по ответу диалога «Сохранить как». Без OCC и Qt."""

import tempfile
import unittest
from pathlib import Path

from cad_io import strings
from cad_io.export_paths import choose_export_target
from cad_io.registry import FormatSpec, Registry

STEP_FILTER = "STEP (*.step *.stp)"
DXF_FILTER = "DXF (*.dxf)"


def _reader(path):
    return path


def _writer(shape, path):
    return None


class ChooseExportTargetTest(unittest.TestCase):
    def setUp(self):
        self.reg = Registry()
        self.step = self.reg.register(
            FormatSpec("STEP", (".step", ".stp"), reader=_reader, writer=_writer)
        )
        self.iges = self.reg.register(FormatSpec("IGES", (".iges", ".igs"), reader=_reader))
        self.dxf = self.reg.register(FormatSpec("DXF", (".dxf",), writer=_writer, kind="2d"))
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)

    def test_step_filter_adds_default_extension(self):
        spec, path = choose_export_target(self.reg, str(self.dir / "part"), STEP_FILTER)
        self.assertIs(spec, self.step)
        self.assertEqual(path, self.dir / "part.step")

    def test_step_filter_keeps_typed_stp(self):
        spec, path = choose_export_target(self.reg, str(self.dir / "part.stp"), STEP_FILTER)
        self.assertIs(spec, self.step)
        self.assertEqual(path, self.dir / "part.stp")

    def test_unknown_filter_uses_extension(self):
        spec, path = choose_export_target(self.reg, str(self.dir / "part.step"), "Что-то (*.*)")
        self.assertIs(spec, self.step)
        self.assertEqual(path, self.dir / "part.step")

    def test_unknown_extension_without_filter(self):
        with self.assertRaises(ValueError) as ctx:
            choose_export_target(self.reg, str(self.dir / "part.txt"), None)
        self.assertEqual(str(ctx.exception), strings.UNKNOWN_FORMAT.format(ext=".txt"))

    def test_wrong_extension_for_selected_filter(self):
        with self.assertRaises(ValueError) as ctx:
            choose_export_target(self.reg, str(self.dir / "part.txt"), STEP_FILTER)
        self.assertEqual(
            str(ctx.exception),
            strings.ERR_BAD_EXT.format(ext=".txt", allowed=".step, .stp"),
        )

    def test_no_extension_and_no_filter(self):
        with self.assertRaises(ValueError) as ctx:
            choose_export_target(self.reg, str(self.dir / "part"), "")
        self.assertEqual(str(ctx.exception), strings.ERR_MISSING_EXT)

    def test_format_without_writer(self):
        with self.assertRaises(ValueError) as ctx:
            choose_export_target(self.reg, str(self.dir / "part.igs"), None)
        self.assertEqual(str(ctx.exception), strings.NO_WRITER.format(name="IGES"))

    def test_empty_path(self):
        for raw in (None, "", "   "):
            with self.subTest(raw=raw):
                with self.assertRaises(ValueError) as ctx:
                    choose_export_target(self.reg, raw, STEP_FILTER)
                self.assertEqual(str(ctx.exception), strings.ERR_EMPTY_PATH)

    def test_existing_file_not_overwritten_when_extension_added(self):
        existing = self.dir / "part.step"
        existing.write_bytes(b"old")
        with self.assertRaises(FileExistsError) as ctx:
            choose_export_target(self.reg, str(self.dir / "part"), STEP_FILTER)
        self.assertEqual(str(ctx.exception), strings.ERR_FILE_EXISTS.format(path=existing))
        self.assertEqual(existing.read_bytes(), b"old")

    def test_existing_file_allowed_when_extension_typed(self):
        existing = self.dir / "part.step"
        existing.write_bytes(b"old")
        spec, path = choose_export_target(self.reg, str(existing), STEP_FILTER)
        self.assertIs(spec, self.step)
        self.assertEqual(path, existing)

    def test_cyrillic_folder(self):
        folder = self.dir / "Модели"
        folder.mkdir()
        spec, path = choose_export_target(self.reg, str(folder / "деталь"), STEP_FILTER)
        self.assertEqual(path, folder / "деталь.step")

    def _assert_wrong_kind(self, ctx, name, spec_kind, kind):
        self.assertEqual(
            str(ctx.exception),
            strings.ERR_WRONG_KIND.format(
                name=name,
                spec_kind=strings.KIND_LABELS[spec_kind],
                kind=strings.KIND_LABELS[kind],
            ),
        )

    def test_2d_filter_rejected_for_3d_export(self):
        with self.assertRaises(ValueError) as ctx:
            choose_export_target(self.reg, str(self.dir / "part"), DXF_FILTER, kind="3d")
        self._assert_wrong_kind(ctx, "DXF", "2d", "3d")
        self.assertFalse((self.dir / "part.dxf").exists())

    def test_2d_extension_rejected_for_3d_export(self):
        # Фильтр не распознан («Все поддерживаемые»), формат берётся по введённому .dxf.
        for selected in (None, strings.ALL_SUPPORTED + " (*.step *.stp)"):
            with self.subTest(selected=selected):
                with self.assertRaises(ValueError) as ctx:
                    choose_export_target(
                        self.reg, str(self.dir / "part.DXF"), selected, kind="3d"
                    )
                self._assert_wrong_kind(ctx, "DXF", "2d", "3d")

    def test_wrong_kind_reported_before_other_errors(self):
        # Тип формата проверяется раньше записи и пути: пользователь узнаёт главную причину.
        self.reg.register(FormatSpec("SVG", (".svg",), reader=_reader, kind="2d"))
        with self.assertRaises(ValueError) as ctx:
            choose_export_target(self.reg, str(self.dir / "part.svg"), None, kind="3d")
        self._assert_wrong_kind(ctx, "SVG", "2d", "3d")
        with self.assertRaises(ValueError) as ctx:
            choose_export_target(self.reg, str(self.dir / "нет" / "part"), DXF_FILTER, kind="3d")
        self._assert_wrong_kind(ctx, "DXF", "2d", "3d")

    def test_2d_extension_typed_with_3d_filter_rejected_as_wrong_kind(self):
        # В диалоге только фильтр STEP, пользователь ввёл part.dxf: Qt вернул STEP_FILTER.
        for name in ("part.dxf", "PART.DXF"):
            with self.subTest(name=name):
                with self.assertRaises(ValueError) as ctx:
                    choose_export_target(self.reg, str(self.dir / name), STEP_FILTER, kind="3d")
                self._assert_wrong_kind(ctx, "DXF", "2d", "3d")
                self.assertFalse((self.dir / name).exists())

    def test_other_extension_typed_with_3d_filter_keeps_bad_ext(self):
        # Формат того же типа (IGES) или неизвестное расширение — дело в расширении, не в типе.
        for ext in (".igs", ".txt"):
            with self.subTest(ext=ext):
                with self.assertRaises(ValueError) as ctx:
                    choose_export_target(
                        self.reg, str(self.dir / ("part" + ext)), STEP_FILTER, kind="3d"
                    )
                self.assertEqual(
                    str(ctx.exception),
                    strings.ERR_BAD_EXT.format(ext=ext, allowed=".step, .stp"),
                )

    def test_2d_extension_typed_with_3d_filter_without_kind(self):
        # Регрессия: без kind прежнее сообщение о расширении не того формата.
        with self.assertRaises(ValueError) as ctx:
            choose_export_target(self.reg, str(self.dir / "part.dxf"), STEP_FILTER)
        self.assertEqual(
            str(ctx.exception),
            strings.ERR_BAD_EXT.format(ext=".dxf", allowed=".step, .stp"),
        )

    def test_bad_kind_rejected_like_qt_filter(self):
        # Недопустимый kind — ошибка аргумента, как в Registry.qt_filter, а не «формат не подходит».
        for kind in ("3D", "2d-ish", ""):
            with self.subTest(kind=kind):
                with self.assertRaises(ValueError) as filter_ctx:
                    self.reg.qt_filter("write", kind=kind)
                with self.assertRaises(ValueError) as ctx:
                    choose_export_target(self.reg, str(self.dir / "part"), STEP_FILTER, kind=kind)
                self.assertEqual(str(ctx.exception), str(filter_ctx.exception))
                self.assertFalse((self.dir / "part.step").exists())

    def test_bad_kind_checked_before_path(self):
        # Ошибка аргумента видна раньше ошибок пути и формата.
        with self.assertRaises(ValueError) as filter_ctx:
            self.reg.qt_filter("write", kind="3D")
        for raw in (None, "", str(self.dir / "part.xyz")):
            with self.subTest(raw=raw):
                with self.assertRaises(ValueError) as ctx:
                    choose_export_target(self.reg, raw, None, kind="3D")
                self.assertEqual(str(ctx.exception), str(filter_ctx.exception))

    def test_3d_format_rejected_for_2d_export(self):
        with self.assertRaises(ValueError) as ctx:
            choose_export_target(self.reg, str(self.dir / "sketch"), STEP_FILTER, kind="2d")
        self._assert_wrong_kind(ctx, "STEP", "3d", "2d")

    def test_matching_kind_accepted(self):
        spec, path = choose_export_target(self.reg, str(self.dir / "part"), STEP_FILTER, kind="3d")
        self.assertIs(spec, self.step)
        self.assertEqual(path, self.dir / "part.step")
        spec, path = choose_export_target(self.reg, str(self.dir / "sketch.dxf"), None, kind="2d")
        self.assertIs(spec, self.dxf)
        self.assertEqual(path, self.dir / "sketch.dxf")

    def test_without_kind_any_format_accepted(self):
        # Регрессия: без kind тип формата не проверяется, как раньше.
        spec, path = choose_export_target(self.reg, str(self.dir / "sketch"), DXF_FILTER)
        self.assertIs(spec, self.dxf)
        self.assertEqual(path, self.dir / "sketch.dxf")
        spec, path = choose_export_target(self.reg, str(self.dir / "sketch.dxf"), None, kind=None)
        self.assertIs(spec, self.dxf)
        self.assertEqual(path, self.dir / "sketch.dxf")


if __name__ == "__main__":
    unittest.main()
