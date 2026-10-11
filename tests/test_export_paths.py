import tempfile
import unittest
from pathlib import Path

from cad_io.export_paths import prepare_export_path


class PrepareExportPathTests(unittest.TestCase):

    def test_missing_extension_with_default(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "модель"

            result = prepare_export_path(
                path,
                default_ext=".step",
            )

            self.assertEqual(
                result,
                Path(directory) / "модель.step",
            )
            self.assertFalse(result.exists())

    def test_missing_extension_without_default(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "модель"

            with self.assertRaisesRegex(
                ValueError,
                "Не указано расширение",
            ):
                prepare_export_path(path)

    def test_uppercase_step_extension_is_allowed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "part.STEP"

            result = prepare_export_path(path)

            self.assertEqual(result, path)
            self.assertFalse(result.exists())

    def test_uppercase_allowed_exts(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "part.igs"

            result = prepare_export_path(
                path,
                allowed_exts=(".IGS",),
            )

            self.assertEqual(result, path)
            self.assertFalse(result.exists())

    def test_path_none(self):
        with self.assertRaisesRegex(
            ValueError,
            "не может быть пустым",
        ):
            prepare_export_path(None)

    def test_disallowed_txt_extension(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "part.txt"

            with self.assertRaisesRegex(
                ValueError,
                "Недопустимое расширение",
            ):
                prepare_export_path(path)

    def test_missing_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "missing" / "part.step"

            with self.assertRaisesRegex(
                FileNotFoundError,
                "Каталог назначения",
            ):
                prepare_export_path(path)

    def test_existing_file_without_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "part.step"
            path.touch()

            with self.assertRaisesRegex(
                FileExistsError,
                "уже существует",
            ):
                prepare_export_path(path)

    def test_existing_file_with_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "part.step"
            path.touch()

            result = prepare_export_path(path, overwrite=True)

            self.assertEqual(result, path)
            self.assertTrue(path.is_file())

    def test_empty_path(self):
        with self.assertRaisesRegex(
            ValueError,
            "не может быть пустым",
        ):
            prepare_export_path("")

    def test_whitespace_only_path(self):
        with self.assertRaisesRegex(
            ValueError,
            "не может быть пустым",
        ):
            prepare_export_path("   ")

    def test_name_with_spaces_and_cyrillic(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "Деталь с пробелами.step"

            result = prepare_export_path(path)

            self.assertEqual(result, path)
            self.assertFalse(result.exists())


if __name__ == "__main__":
    unittest.main()
