import unittest
import tempfile
import json
from pathlib import Path

import core.subtitle_input as subtitle_input_module

from core.subtitle_input import (
    clear_task_input_state,
    clear_generated_subtitle_outputs,
    combined_source_text,
    has_official_source,
    load_source_srt,
    parse_srt,
    render_subtitle_variants,
    save_source_srt,
    translate_and_write_official_subtitles,
    translate_official_cues,
    write_subtitle_variants,
)


OFFICIAL_SRT = """\ufeff10\r
00:00:20,000 --> 00:00:24,000\r
Example  sentence.\r
Second source line.\r
\r
42\r
00:01:15,200 --> 00:01:19,600\r
This house has belonged to the family for more than three hundred years.\r
"""


class SubtitleInputTests(unittest.TestCase):
    def test_parser_preserves_source_cue_fields_and_text(self):
        cues = parse_srt(OFFICIAL_SRT)

        self.assertEqual([cue.stable_id for cue in cues], ["cue-000001", "cue-000002"])
        self.assertEqual(cues[0].index, "10")
        self.assertEqual(cues[0].start, "00:00:20,000")
        self.assertEqual(cues[0].end, "00:00:24,000")
        self.assertEqual(cues[0].text, "Example  sentence.\nSecond source line.")
        self.assertEqual(cues[1].index, "42")

    def test_renderer_preserves_original_timing_line_settings_and_spacing(self):
        source = (
            "7\n"
            "  00:00:01,000  -->  00:00:02,500 align:start position:10%  \n"
            "Positioned subtitle.\n"
        )
        cues = parse_srt(source)

        outputs = render_subtitle_variants(cues, {"cue-000001": "定位字幕。"})

        self.assertIn(
            "7\n  00:00:01,000  -->  00:00:02,500 align:start position:10%  \n"
            "Positioned subtitle.\n",
            outputs["src.srt"],
        )

    def test_parser_skips_empty_cue_but_rejects_malformed_nonempty_cue(self):
        with_empty = """1
00:00:01,000 --> 00:00:02,000


2
00:00:03,000 --> 00:00:04,000
Kept.
"""
        self.assertEqual([cue.index for cue in parse_srt(with_empty)], ["2"])

        malformed = """1
not a timestamp
Text must not be silently shifted.
"""
        with self.assertRaisesRegex(ValueError, "cue 1"):
            parse_srt(malformed)

    def test_rendered_variants_keep_original_metadata_order_and_source_text(self):
        cues = parse_srt(OFFICIAL_SRT)
        translations = {
            "cue-000002": "这座庄园属于这个家族已经三百多年了。",
            "cue-000001": "示例句。",
        }

        outputs = render_subtitle_variants(cues, translations)

        self.assertEqual(
            outputs["src.srt"],
            "10\n00:00:20,000 --> 00:00:24,000\n"
            "Example  sentence.\nSecond source line.\n\n"
            "42\n00:01:15,200 --> 00:01:19,600\n"
            "This house has belonged to the family for more than three hundred years.\n",
        )
        for name in ("src.srt", "trans.srt", "src_trans.srt", "trans_src.srt"):
            self.assertIn("10\n00:00:20,000 --> 00:00:24,000\n", outputs[name])
            self.assertIn("42\n00:01:15,200 --> 00:01:19,600\n", outputs[name])

        self.assertIn(
            "Example  sentence.\nSecond source line.\n示例句。",
            outputs["src_trans.srt"],
        )
        self.assertIn(
            "示例句。\nExample  sentence.\nSecond source line.",
            outputs["trans_src.srt"],
        )

    def test_translation_batches_restore_results_by_stable_id(self):
        cues = parse_srt(OFFICIAL_SRT)
        calls = []

        def fake_translate(items, previous_content, after_content, batch_index):
            calls.append((items, previous_content, after_content, batch_index))
            return {
                item["id"]: f"translated:{item['id']}"
                for item in reversed(items)
            }

        translations = translate_official_cues(
            cues,
            fake_translate,
            max_batch_items=10,
            max_batch_chars=2000,
        )

        self.assertEqual(
            translations,
            {
                "cue-000001": "translated:cue-000001",
                "cue-000002": "translated:cue-000002",
            },
        )
        self.assertEqual(
            calls[0][0][0],
            {"id": "cue-000001", "text": "Example  sentence. Second source line."},
        )
        self.assertEqual(cues[0].text, "Example  sentence.\nSecond source line.")

    def test_summary_source_uses_all_cues_without_mutating_source(self):
        cues = parse_srt(OFFICIAL_SRT)

        summary_source = combined_source_text(cues)

        self.assertEqual(
            summary_source,
            "Example  sentence. Second source line.\n"
            "This house has belonged to the family for more than three hundred years.",
        )
        self.assertEqual(cues[0].text, "Example  sentence.\nSecond source line.")

    def test_official_translation_adapter_writes_variants_from_id_mapping(self):
        cues = parse_srt(OFFICIAL_SRT)

        def fake_translate(items, previous_content, after_content, batch_index):
            return {item["id"]: f"translated:{item['id']}" for item in items}

        with tempfile.TemporaryDirectory() as output_dir:
            written = translate_and_write_official_subtitles(
                cues,
                video_style="style snapshot",
                output_dir=output_dir,
                translate_batch=fake_translate,
            )

            self.assertEqual(len(written), 4)
            trans_srt = (Path(output_dir) / "trans.srt").read_text(encoding="utf-8")

        self.assertIn("translated:cue-000001", trans_srt)
        self.assertIn("translated:cue-000002", trans_srt)

    def test_writer_creates_exactly_the_four_expected_srt_files(self):
        cues = parse_srt(OFFICIAL_SRT)
        translations = {
            "cue-000001": "示例句。",
            "cue-000002": "这座庄园属于这个家族已经三百多年了。",
        }

        with tempfile.TemporaryDirectory() as output_dir:
            written = write_subtitle_variants(cues, translations, output_dir)

            self.assertEqual(
                [Path(path).name for path in written],
                ["src.srt", "trans.srt", "src_trans.srt", "trans_src.srt"],
            )
            self.assertEqual(
                sorted(path.name for path in Path(output_dir).iterdir()),
                ["src.srt", "src_trans.srt", "trans.srt", "trans_src.srt"],
            )
            self.assertEqual(
                (Path(output_dir) / "src.srt").read_text(encoding="utf-8"),
                render_subtitle_variants(cues, translations)["src.srt"],
            )

    def test_structured_source_snapshot_preserves_authoritative_fields(self):
        cues = parse_srt(OFFICIAL_SRT)
        snapshot_writer = getattr(subtitle_input_module, "save_structured_cues", None)
        self.assertTrue(callable(snapshot_writer), "structured cue snapshot writer is missing")

        with tempfile.TemporaryDirectory() as output_dir:
            path = Path(output_dir) / "source_subtitles.json"
            snapshot_writer(cues, path)
            data = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(
            data[0],
            {
                "stable_id": "cue-000001",
                "index": "10",
                "start": "00:00:20,000",
                "end": "00:00:24,000",
                "timing_line": "00:00:20,000 --> 00:00:24,000",
                "text": "Example  sentence.\nSecond source line.",
            },
        )

    def test_translation_batch_rejects_missing_cue_id(self):
        cues = parse_srt(OFFICIAL_SRT)

        def incomplete_translate(items, previous_content, after_content, batch_index):
            return {items[0]["id"]: "only one result"}

        with self.assertRaisesRegex(ValueError, "cue-000002"):
            translate_official_cues(cues, incomplete_translate)

    def test_task_input_cleanup_prevents_previous_video_state_leak(self):
        state = {
            "_source_srt_uploader": object(),
            "_source_srt_upload_id": "A.srt:123",
            "_source_srt_name": "A.srt",
            "_source_srt_error": "invalid old subtitle",
            "_video_style_input": "style A",
            "_video_style_snapshot": "style A",
            "_subtitle_zip_selection": ["trans.srt"],
            "unrelated": "keep",
        }

        clear_task_input_state(state)

        self.assertEqual(state, {"unrelated": "keep"})

    def test_source_upload_is_validated_saved_and_loaded_without_rewriting_cues(self):
        payload = OFFICIAL_SRT.encode("utf-8")
        with tempfile.TemporaryDirectory() as output_dir:
            path = Path(output_dir) / "log" / "source_input.srt"

            saved_cues = save_source_srt(payload, path)
            loaded_cues = load_source_srt(path)

            self.assertTrue(has_official_source(path))
            self.assertEqual(path.read_bytes(), payload)
            self.assertEqual(saved_cues, loaded_cues)
            self.assertEqual(loaded_cues[0].index, "10")
            self.assertEqual(loaded_cues[0].text, "Example  sentence.\nSecond source line.")

    def test_mode_change_clears_generated_subtitles_but_keeps_media_and_source_upload(self):
        with tempfile.TemporaryDirectory() as output_dir:
            output = Path(output_dir)
            media = output / "video.mp4"
            source_input = output / "log" / "source_input.srt"
            derived = (
                output / "src.srt",
                output / "trans.srt",
                output / ".subtitle_done",
                output / "log" / "terminology.json",
            )
            media.write_bytes(b"video")
            source_input.parent.mkdir(parents=True)
            source_input.write_text("source", encoding="utf-8")
            for path in derived:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("derived", encoding="utf-8")

            clear_generated_subtitle_outputs(output)

            self.assertTrue(media.exists())
            self.assertTrue(source_input.exists())
            self.assertTrue(all(not path.exists() for path in derived))


if __name__ == "__main__":
    unittest.main()
