import importlib.util
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class _EmptyTerms:
    def __len__(self):
        return 0

    def iterrows(self):
        return iter(())


class _DummyConsole:
    def print(self, *args, **kwargs):
        pass


def _temporary_modules(replacements):
    class _ModuleContext:
        def __enter__(self):
            self.saved = {name: sys.modules.get(name) for name in replacements}
            sys.modules.update(replacements)

        def __exit__(self, exc_type, exc, traceback):
            for name, module in self.saved.items():
                if module is None:
                    sys.modules.pop(name, None)
                else:
                    sys.modules[name] = module

    return _ModuleContext()


def _core_package():
    package = types.ModuleType("core")
    package.__path__ = [str(PROJECT_ROOT / "core")]
    return package


def _load_summarize_module():
    pandas_stub = types.ModuleType("pandas")
    pandas_stub.read_excel = lambda path: _EmptyTerms()

    prompts_stub = types.ModuleType("core.prompts")
    prompts_stub.get_summary_prompt = lambda *args, **kwargs: "summary prompt"

    utils_stub = types.ModuleType("core.utils")
    utils_stub.load_key = lambda key: 10_000
    utils_stub.rprint = lambda *args, **kwargs: None
    utils_stub.ask_gpt = lambda *args, **kwargs: {"theme": "theme", "terms": []}
    utils_stub.__all__ = ["load_key", "rprint", "ask_gpt"]

    models_stub = types.ModuleType("core.utils.models")
    models_stub._3_2_SPLIT_BY_MEANING = "unused.txt"
    models_stub._4_1_TERMINOLOGY = "unused.json"

    replacements = {
        "core": _core_package(),
        "core.prompts": prompts_stub,
        "core.utils": utils_stub,
        "core.utils.models": models_stub,
        "pandas": pandas_stub,
    }
    with _temporary_modules(replacements):
        spec = importlib.util.spec_from_file_location(
            "videolingo_summarize_under_test",
            PROJECT_ROOT / "core" / "_4_1_summarize.py",
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    return module


def _load_translate_module():
    pandas_stub = types.ModuleType("pandas")

    translate_stub = types.ModuleType("core.translate_lines")
    translate_stub.translate_lines = lambda *args, **kwargs: ("translated", "source")

    summarize_stub = types.ModuleType("core._4_1_summarize")
    summarize_stub.search_things_to_note_in_prompt = lambda text: None

    audio_stub = types.ModuleType("core._8_1_audio_task")
    audio_stub.check_len_then_trim = lambda text, duration: text

    subtitle_stub = types.ModuleType("core._6_gen_sub")
    subtitle_stub.align_timestamp = lambda *args, **kwargs: None

    def passthrough_decorator(path):
        return lambda func: func

    utils_stub = types.ModuleType("core.utils")
    utils_stub.check_file_exists = passthrough_decorator
    utils_stub.load_key = lambda key: 1
    utils_stub.check_cancel = lambda: None
    utils_stub.__all__ = ["check_file_exists", "load_key", "check_cancel"]

    models_stub = types.ModuleType("core.utils.models")
    for name, value in {
        "_3_2_SPLIT_BY_MEANING": "split.txt",
        "_4_1_TERMINOLOGY": "terms.json",
        "_4_2_TRANSLATION": "translation.xlsx",
        "_2_CLEANED_CHUNKS": "cleaned.xlsx",
    }.items():
        setattr(models_stub, name, value)
    models_stub.__all__ = [
        "_3_2_SPLIT_BY_MEANING",
        "_4_1_TERMINOLOGY",
        "_4_2_TRANSLATION",
        "_2_CLEANED_CHUNKS",
    ]

    rich_console = types.ModuleType("rich.console")
    rich_console.Console = _DummyConsole
    rich_progress = types.ModuleType("rich.progress")
    rich_progress.Progress = object
    rich_progress.SpinnerColumn = object
    rich_progress.TextColumn = object

    replacements = {
        "core": _core_package(),
        "core.translate_lines": translate_stub,
        "core._4_1_summarize": summarize_stub,
        "core._8_1_audio_task": audio_stub,
        "core._6_gen_sub": subtitle_stub,
        "core.utils": utils_stub,
        "core.utils.models": models_stub,
        "pandas": pandas_stub,
        "rich.console": rich_console,
        "rich.progress": rich_progress,
    }
    with _temporary_modules(replacements):
        spec = importlib.util.spec_from_file_location(
            "videolingo_translate_pipeline_under_test",
            PROJECT_ROOT / "core" / "_4_2_translate.py",
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    return module


class PipelineStyleTests(unittest.TestCase):
    def test_summary_entry_passes_explicit_source_and_style_to_prompt(self):
        module = _load_summarize_module()
        captured = {}

        def capture_prompt(source_content, custom_terms_json=None, video_style=None):
            captured.update(
                source_content=source_content,
                custom_terms_json=custom_terms_json,
                video_style=video_style,
            )
            return "summary prompt"

        module.get_summary_prompt = capture_prompt
        module.ask_gpt = lambda *args, **kwargs: {"theme": "theme", "terms": []}

        with tempfile.TemporaryDirectory() as temp_dir:
            module._4_1_TERMINOLOGY = str(Path(temp_dir) / "terminology.json")
            module.get_summary(
                source_content="Official cue source",
                video_style="Style snapshot",
            )
            saved = json.loads(Path(module._4_1_TERMINOLOGY).read_text(encoding="utf-8"))

        self.assertEqual(captured["source_content"], "Official cue source")
        self.assertEqual(captured["video_style"], "Style snapshot")
        self.assertEqual(saved["theme"], "theme")

    def test_regular_translation_chunk_forwards_style_snapshot(self):
        module = _load_translate_module()
        captured = {}

        def capture_translate(*args, **kwargs):
            captured.update(kwargs)
            return "translated", "source"

        module.translate_lines = capture_translate

        module.translate_chunk(
            "source",
            ["source"],
            "theme",
            0,
            video_style="Style snapshot",
        )

        self.assertEqual(captured["video_style"], "Style snapshot")


if __name__ == "__main__":
    unittest.main()
