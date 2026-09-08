import io
import tempfile
import unittest
import zipfile
from pathlib import Path


from core.subtitle_zip import build_subtitle_zip_bytes, build_subtitle_download


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

    def test_single_download_returns_original_srt_bytes(self):
        for name in ("src.srt", "trans.srt", "src_trans.srt", "trans_src.srt"):
            data, filename, mime = build_subtitle_download(self.temp_dir.name, [name])
            self.assertEqual(data, (Path(self.temp_dir.name) / name).read_bytes())
            self.assertEqual(filename, name)
            self.assertEqual(mime, "application/x-subrip")

    def test_multiple_download_returns_selected_zip(self):
        selected = ["trans.srt", "trans_src.srt"]
        data, filename, mime = build_subtitle_download(self.temp_dir.name, selected)
        self.assertEqual((filename, mime), ("subtitles.zip", "application/zip"))
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            self.assertEqual(archive.namelist(), selected)

    def test_video_name_is_preserved_in_single_and_all_zip_entries(self):
        stem = "ISS - Full Of Stars · 4K · HDR"
        media_name = stem + ".mp4"
        data, filename, _ = build_subtitle_download(self.temp_dir.name, ["trans.srt"], media_name)
        self.assertEqual(filename, f"tran丨{stem}.srt")
        self.assertEqual(data, b"contents:trans.srt")
        selected = ["src.srt", "trans.srt", "src_trans.srt", "trans_src.srt"]
        data, filename, _ = build_subtitle_download(self.temp_dir.name, selected, media_name)
        self.assertEqual(filename, f"subtitles丨{stem}.zip")
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            expected = [f"{prefix}丨{stem}.srt" for prefix in ["src", "tran", "src_trans", "trans_src"]]
            self.assertEqual(archive.namelist(), expected)
            for source, target in zip(selected, expected):
                self.assertEqual(archive.read(target), (Path(self.temp_dir.name) / source).read_bytes())

    def test_download_rejects_empty_invalid_duplicate_and_missing_files(self):
        for selected in ([], ["../src.srt"], ["src.srt", "src.srt"]):
            with self.assertRaises(ValueError):
                build_subtitle_download(self.temp_dir.name, selected)
        (Path(self.temp_dir.name) / "src.srt").unlink()
        with self.assertRaises(FileNotFoundError):
            build_subtitle_download(self.temp_dir.name, ["src.srt"])

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
