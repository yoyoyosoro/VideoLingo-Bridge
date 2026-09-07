import importlib.util
import sys
import types
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
core_package = types.ModuleType("core")
core_package.__path__ = [str(PROJECT_ROOT / "core")]
utils_stub = types.ModuleType("core.utils")
utils_stub.__all__ = []
sys.modules.setdefault("core", core_package)
sys.modules["core.utils"] = utils_stub

spec = importlib.util.spec_from_file_location(
    "videolingo_prompts_under_test",
    PROJECT_ROOT / "core" / "prompts.py",
)
prompts = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prompts)


class PromptContextTests(unittest.TestCase):
    def setUp(self):
        self.original_load_key = getattr(prompts, "load_key", None)
        values = {
            "whisper.detected_language": "en",
            "target_language": "简体中文",
        }
        prompts.load_key = values.__getitem__

    def tearDown(self):
        if self.original_load_key is None:
            delattr(prompts, "load_key")
        else:
            prompts.load_key = self.original_load_key

    def test_empty_style_keeps_shared_prompt_free_of_style_section(self):
        result = prompts.generate_shared_prompt(None, None, "summary", None, video_style="  ")

        self.assertNotIn("User Video Context / Style Guidance", result)

    def test_style_is_injected_into_shared_translation_prompt(self):
        style = "这是英国庄园 Room Tour，翻译自然口语化。"

        result = prompts.generate_shared_prompt(None, None, "summary", None, video_style=style)

        self.assertIn("### User Video Context / Style Guidance", result)
        self.assertIn(style, result)

    def test_style_is_available_to_summary_prompt(self):
        style = "这是硬核天文学科普，术语必须准确。"

        result = prompts.get_summary_prompt("Source text", video_style=style)

        self.assertIn("### User Video Context / Style Guidance", result)
        self.assertIn(style, result)

    def test_default_translation_schema_keeps_existing_numeric_placeholder(self):
        result = prompts.get_prompt_faithfulness("Alpha\nBeta", "shared")

        self.assertIn("direct 简体中文 translation 1.", result)
        self.assertIn("direct 简体中文 translation 2.", result)


if __name__ == "__main__":
    unittest.main()
