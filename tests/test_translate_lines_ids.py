import importlib.util
import sys
import types
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class _DummyConsole:
    def print(self, *args, **kwargs):
        return None


class _DummyTable:
    def __init__(self, *args, **kwargs):
        pass

    def add_column(self, *args, **kwargs):
        pass

    def add_row(self, *args, **kwargs):
        pass


def _load_translate_module():
    names = (
        "core",
        "core.utils",
        "core.prompts",
        "rich",
        "rich.panel",
        "rich.console",
        "rich.table",
    )
    saved = {name: sys.modules.get(name) for name in names}
    try:
        core_package = types.ModuleType("core")
        core_package.__path__ = [str(PROJECT_ROOT / "core")]

        utils_stub = types.ModuleType("core.utils")
        utils_stub.check_cancel = lambda: None
        utils_stub.load_key = lambda key: False if key == "reflect_translate" else "en"
        utils_stub.ask_gpt = lambda *args, **kwargs: None
        utils_stub.__all__ = ["check_cancel", "load_key", "ask_gpt"]

        rich_stub = types.ModuleType("rich")
        rich_stub.box = types.SimpleNamespace(ROUNDED=None)
        panel_stub = types.ModuleType("rich.panel")
        panel_stub.Panel = lambda *args, **kwargs: None
        console_stub = types.ModuleType("rich.console")
        console_stub.Console = _DummyConsole
        table_stub = types.ModuleType("rich.table")
        table_stub.Table = _DummyTable

        sys.modules.update(
            {
                "core": core_package,
                "core.utils": utils_stub,
                "rich": rich_stub,
                "rich.panel": panel_stub,
                "rich.console": console_stub,
                "rich.table": table_stub,
            }
        )

        prompts_spec = importlib.util.spec_from_file_location(
            "core.prompts", PROJECT_ROOT / "core" / "prompts.py"
        )
        prompts_module = importlib.util.module_from_spec(prompts_spec)
        sys.modules["core.prompts"] = prompts_module
        prompts_spec.loader.exec_module(prompts_module)

        translate_spec = importlib.util.spec_from_file_location(
            "videolingo_translate_lines_under_test",
            PROJECT_ROOT / "core" / "translate_lines.py",
        )
        translate_module = importlib.util.module_from_spec(translate_spec)
        translate_spec.loader.exec_module(translate_module)
        return translate_module, prompts_module
    finally:
        for name, module in saved.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module


translate_lines_module, prompts_module = _load_translate_module()


class TranslateLineIdTests(unittest.TestCase):
    def setUp(self):
        translate_lines_module.check_cancel = lambda: None
        translate_lines_module.load_key = (
            lambda key: False if key == "reflect_translate" else "en"
        )
        prompts_module.load_key = lambda key: {
            "target_language": "简体中文",
            "whisper.detected_language": "en",
        }[key]

    def test_custom_ids_restore_model_results_in_input_order(self):
        seen_prompts = []

        def fake_ask_gpt(prompt, **kwargs):
            seen_prompts.append(prompt)
            return {
                "cue-000002": {"origin": "Beta", "direct": "译文二"},
                "cue-000001": {"origin": "Alpha", "direct": "译文一"},
            }

        translate_lines_module.ask_gpt = fake_ask_gpt

        translated, source = translate_lines_module.translate_lines(
            "Alpha\nBeta",
            None,
            None,
            None,
            "summary",
            item_ids=["cue-000001", "cue-000002"],
            video_style="自然口语化",
        )

        self.assertEqual(source, "Alpha\nBeta")
        self.assertEqual(translated, "译文一\n译文二")
        self.assertIn("cue-000001", seen_prompts[0])
        self.assertIn("cue-000002", seen_prompts[0])
        self.assertIn("自然口语化", seen_prompts[0])

    def test_validator_rejects_unexpected_id(self):
        result = {
            "cue-000001": {"direct": "one"},
            "cue-000002": {"direct": "two"},
            "cue-extra": {"direct": "must be rejected"},
        }

        validation = translate_lines_module.valid_translate_result(
            result,
            ["cue-000001", "cue-000002"],
            ["direct"],
        )

        self.assertEqual(validation["status"], "error")
        self.assertIn("cue-extra", validation["message"])

    def test_validator_rejects_non_object_cue_result_without_crashing(self):
        validation = translate_lines_module.valid_translate_result(
            {"cue-000001": "not an object"},
            ["cue-000001"],
            ["direct"],
        )

        self.assertEqual(validation["status"], "error")
        self.assertIn("cue-000001", validation["message"])


if __name__ == "__main__":
    unittest.main()
