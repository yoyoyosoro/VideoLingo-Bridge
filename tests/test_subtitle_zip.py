import io
import tempfile
import unittest
import zipfile
from pathlib import Path


from core.subtitle_zip import build_subtitle_zip_bytes


class SubtitleZipTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        output = Path(self.temp_dir.name)
        for name in ("src.srt", "trans.srt", "src_trans.srt", "trans_src.srt"):
            (output / name).write_text(f"contents:{name}", encoding="utf-8")
        (output / "unrelated.srt").write_text("must not leak", encoding="utf-8")

    def tearDown(self):
        self.temp_dir.cleanup()

    def _read_zip(self, selected):
        data = build_subtitle_zip_bytes(self.temp_dir.name, selected)
        return zipfile.ZipFile(io.BytesIO(data), "r")

    def test_single_selection_contains_only_translation(self):
        with self._read_zip(["trans.srt"]) as archive:
            self.assertEqual(archive.namelist(), ["trans.srt"])
            self.assertEqual(archive.read("trans.srt").decode(), "contents:trans.srt")

    def test_combined_selection_contains_only_requested_files_in_requested_order(self):
        with self._read_zip(["src.srt", "src_trans.srt"]) as archive:
            self.assertEqual(archive.namelist(), ["src.srt", "src_trans.srt"])

    def test_all_four_matches_existing_download_scope_without_unrelated_srt(self):
        selected = ["src.srt", "trans.srt", "src_trans.srt", "trans_src.srt"]
        with self._read_zip(selected) as archive:
            self.assertEqual(archive.namelist(), selected)

    def test_empty_selection_does_not_build_an_empty_zip(self):
        with self.assertRaisesRegex(ValueError, "at least one"):
            build_subtitle_zip_bytes(self.temp_dir.name, [])


if __name__ == "__main__":
    unittest.main()
