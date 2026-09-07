import importlib.util
import sys
import types
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _load_st_module():
    calls = []

    streamlit = types.ModuleType("streamlit")
    streamlit.set_page_config = lambda **kwargs: None
    streamlit.fragment = lambda **kwargs: (lambda func: func)
    streamlit.session_state = {}

    def record(name):
        def inner(*args, **kwargs):
            calls.append((name, args, kwargs))
        return inner

    modules = {
        "_1_ytdlp": types.SimpleNamespace(),
        "_2_asr": types.SimpleNamespace(transcribe=record("asr")),
        "_3_1_split_nlp": types.SimpleNamespace(split_by_spacy=record("split_nlp")),
        "_3_2_split_meaning": types.SimpleNamespace(
            split_sentences_by_meaning=record("split_meaning")
        ),
        "_4_1_summarize": types.SimpleNamespace(get_summary=record("summary")),
        "_4_2_translate": types.SimpleNamespace(translate_all=record("translate")),
        "_5_split_sub": types.SimpleNamespace(split_for_sub_main=record("split_sub")),
        "_6_gen_sub": types.SimpleNamespace(align_timestamp_main=record("align")),
        "_7_sub_into_vid": types.SimpleNamespace(
            merge_subtitles_to_video=record("merge_subtitles")
        ),
        "_8_1_audio_task": types.SimpleNamespace(gen_audio_task_main=record("audio_task")),
        "_8_2_dub_chunks": types.SimpleNamespace(dub_chunks=record("dub_chunks")),
        "_9_refer_audio": types.SimpleNamespace(extract_refer_audio_main=record("refer")),
        "_10_gen_audio": types.SimpleNamespace(gen_audio=record("gen_audio")),
        "_11_merge_audio": types.SimpleNamespace(merge_full_audio=record("merge_audio")),
        "_12_dub_to_vid": types.SimpleNamespace(merge_video_audio=record("merge_video")),
    }
    core_package = types.ModuleType("core")
    core_package.__path__ = [str(PROJECT_ROOT / "core")]
    for name, module in modules.items():
        setattr(core_package, name, module)
    core_package.__all__ = list(modules)

    imports_stub = types.ModuleType("core.st_utils.imports_and_utils")
    imports_stub.t = lambda text: text
    imports_stub.load_key = lambda key: False
    imports_stub.update_key = record("update_key")
    imports_stub.__all__ = ["t", "load_key", "update_key"]

    task_runner_stub = types.ModuleType("core.st_utils.task_runner")
    task_runner_stub.TaskRunner = object

    translations_stub = types.ModuleType("translations.translations")
    translations_stub.DISPLAY_LANGUAGES = {}
    translations_stub.init_display_language = lambda: None
    translations_stub.set_display_language = lambda language: None

    models_stub = types.ModuleType("core.utils.models")
    models_stub._TEXT_DONE_MARKER = "output/.subtitle_done"
    models_stub._AUDIO_DONE_MARKER = "output/.dubbing_done"

    subtitle_input_stub = types.ModuleType("core.subtitle_input")
    subtitle_input_stub.combined_source_text = lambda cues: "combined source"
    subtitle_input_stub.has_official_source = lambda: False
    subtitle_input_stub.load_source_srt = lambda: []
    subtitle_input_stub.save_structured_cues = record("save_structured")
    subtitle_input_stub.translate_and_write_official_subtitles = record(
        "official_translate"
    )
    subtitle_input_stub.clear_task_input_state = record("clear_task_state")

    replacements = {
        "streamlit": streamlit,
        "core": core_package,
        "core.st_utils.imports_and_utils": imports_stub,
        "core.st_utils.task_runner": task_runner_stub,
        "core.utils.models": models_stub,
        "core.subtitle_input": subtitle_input_stub,
        "translations.translations": translations_stub,
    }
    saved = {name: sys.modules.get(name) for name in replacements}
    try:
        sys.modules.update(replacements)
        spec = importlib.util.spec_from_file_location(
            "videolingo_st_under_test", PROJECT_ROOT / "st.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        for name, previous in saved.items():
            if previous is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = previous
    return module, modules, calls


class TextPipelineStepTests(unittest.TestCase):
    def test_regular_mode_keeps_asr_and_forwards_style_snapshot(self):
        module, modules, calls = _load_st_module()

        steps = module._get_text_steps(video_style="Style A")
        steps[2][1]()

        self.assertIs(steps[0][1], modules["_2_asr"].transcribe)
        self.assertIn(("summary", (), {"video_style": "Style A"}), calls)
        self.assertIn(("translate", (), {"video_style": "Style A"}), calls)

    def test_official_mode_contains_no_asr_and_uses_direct_subtitle_pipeline(self):
        module, modules, calls = _load_st_module()
        cues = ("cue-one", "cue-two")

        steps = module._get_text_steps(
            official_cues=cues,
            video_style="Style B",
        )
        steps[0][1]()
        steps[1][1]()

        self.assertNotIn(modules["_2_asr"].transcribe, [step[1] for step in steps])
        self.assertIn(("save_structured", (cues,), {}), calls)
        self.assertIn(
            (
                "summary",
                (),
                {"source_content": "combined source", "video_style": "Style B"},
            ),
            calls,
        )
        self.assertIn(
            ("official_translate", (cues,), {"video_style": "Style B"}),
            calls,
        )


if __name__ == "__main__":
    unittest.main()
