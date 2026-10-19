"""Exercise native Messages over local HTTP; never call a paid provider."""
import importlib.util
import json
import sys
import types
import sqlite3
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

import pytest


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def api(tmp_path):
    spec = importlib.util.spec_from_file_location(
        "llm_api_under_test", ROOT / "core/utils/llm_api.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    folder = tmp_path / "cc-switch"
    folder.mkdir()
    (folder / "live-state.json").write_text(json.dumps({"apps": {"claude": {
        "mode": "proxy", "proxy_route": "claude-provider"}}}), encoding="utf-8")
    with sqlite3.connect(folder / "cc-switch.db") as db:
        db.executescript("CREATE TABLE providers (id TEXT, app_type TEXT, meta TEXT, settings_config TEXT, is_current INTEGER);"
                         "CREATE TABLE proxy_config (app_type TEXT, enabled INTEGER, auto_failover_enabled INTEGER);"
                         "INSERT INTO proxy_config VALUES ('claude', 1, 0);")
        for provider, wire, model in (("claude-provider", "anthropic", "claude-mapped"),
                                      ("gpt-provider", "openai_chat", "gpt-mapped"),
                                      ("gemini-provider", "gemini_native", "gemini-mapped")):
            settings = {"env": {"ANTHROPIC_DEFAULT_SONNET_MODEL": model,
                                "ANTHROPIC_AUTH_TOKEN": "credential-must-never-be-logged"}}
            db.execute("INSERT INTO providers VALUES (?, 'claude', ?, ?, ?)",
                       (provider, json.dumps({"apiFormat": wire}), json.dumps(settings), int(provider == "claude-provider")))
    original = module.cc_switch_route_identity
    module.cc_switch_route_identity = lambda: original(folder)
    module.route_folder = folder
    return module


@pytest.fixture
def endpoint():
    state = {"requests": [], "status": 200, "response": {
        "model": "claude-sonnet-5-5",
        "content": [
            {"type": "thinking", "thinking": "private reasoning"},
            {"type": "text", "text": '{"message":"success"}'},
        ],
        "stop_reason": "end_turn",
        "usage": {"input_tokens": 20, "output_tokens": 30,
                  "cache_creation_input_tokens": 512, "cache_read_input_tokens": 0},
    }}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            state["requests"].append((self.path, dict(self.headers), body))
            encoded = json.dumps(state["response"]).encode()
            self.send_response(state["status"])
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", state
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_cc_switch_uses_code_route_placeholder_auth_and_low_effort(api, endpoint, monkeypatch):
    base, state = endpoint
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:1")
    monkeypatch.setenv("NO_PROXY", "")
    text, metadata = api.request_anthropic(
        "Test", model="claude-sonnet-5-5", base_url=base,
        api_key="unused-real-key", cc_switch=True,
        effort="low",
    )
    path, headers, body = state["requests"][0]
    assert path == "/v1/messages"
    assert headers["x-api-key"] == "cc-switch-proxy"
    assert "unused-real-key" not in json.dumps(headers)
    assert body["output_config"] == {"effort": "low"}
    assert body["max_tokens"] == 8192
    assert text == '{"message":"success"}'
    assert metadata["usage"]["output_tokens"] == 30
    assert metadata["stop_reason"] == "end_turn"


@pytest.mark.parametrize("suffix", ["", "/v1", "/v1/messages"])
def test_native_endpoint_normalization_and_auth(api, endpoint, suffix):
    base, state = endpoint
    api.request_anthropic("Test", model="claude-sonnet-5-5",
                          base_url=base + suffix, api_key="test-key")
    path, headers, _ = state["requests"][0]
    assert path == "/v1/messages"
    assert headers["x-api-key"] == "test-key"
    assert headers["anthropic-version"] == "2023-06-01"


def test_cache_marks_stable_prefix_not_changing_subtitle(api, endpoint):
    base, state = endpoint
    prefix = "## Role\nTranslate faithfully.\n"
    for source in ("First sentence.", "Second sentence."):
        api.request_anthropic(prefix + "\n## INPUT\n" + source,
                              model="claude-sonnet-5-5", base_url=base,
                              api_key="test-key")
    first, second = [r[2] for r in state["requests"]]
    assert first["system"] == second["system"]
    assert first["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert "First sentence." in first["messages"][0]["content"]
    assert "Second sentence." in second["messages"][0]["content"]
    assert "cache_control" not in first


def test_cache_can_be_disabled_and_dynamic_context_stays_in_user(api, endpoint):
    base, state = endpoint
    prompt = "## Role\nTranslate.\n\n### Context Information\nprevious sentence\n## INPUT\ntext"
    api.request_anthropic(prompt, model="claude-sonnet-5-5", base_url=base,
                          api_key="test-key", prompt_cache=False)
    body = state["requests"][0][2]
    assert "cache_control" not in json.dumps(body)
    assert "previous sentence" not in body["system"][0]["text"]
    assert "previous sentence" in body["messages"][0]["content"]


@pytest.mark.parametrize("reason", ["max_tokens", "refusal"])
def test_truncated_or_refused_answer_is_not_accepted(api, endpoint, reason):
    base, state = endpoint
    state["response"]["stop_reason"] = reason
    with pytest.raises(api.LLMResponseError) as caught:
        api.request_anthropic("Test", model="claude-sonnet-5-5",
                              base_url=base, api_key="test-key")
    assert caught.value.metadata["usage"]["output_tokens"] == 30


def test_empty_answer_is_rejected(api, endpoint):
    base, state = endpoint
    state["response"]["content"] = [{"type": "thinking", "thinking": "only thinking"}]
    with pytest.raises(api.LLMResponseError):
        api.request_anthropic("Test", model="claude-sonnet-5-5",
                              base_url=base, api_key="test-key")


def test_cc_switch_rejects_desktop_route_before_sending(api, endpoint):
    base, state = endpoint
    with pytest.raises(api.LLMResponseError):
        api.request_anthropic("Test", model="claude-sonnet-5-5",
                              base_url=base + "/claude-desktop", api_key="unused",
                              cc_switch=True)
    assert not state["requests"]


def test_older_claude_does_not_receive_unsupported_effort(api, endpoint):
    base, state = endpoint
    api.request_anthropic("Test", model="claude-sonnet-4-20250514",
                          base_url=base, api_key="test-key")
    assert "output_config" not in state["requests"][0][2]


@pytest.fixture
def ask(api, endpoint, monkeypatch, tmp_path):
    # Import only the request code, without initializing ASR/ML dependencies.
    for name, path in (("core", "core"), ("core.utils", "core/utils")):
        package = types.ModuleType(name)
        package.__path__ = [str(ROOT / path)]
        monkeypatch.setitem(sys.modules, name, package)
    config_spec = importlib.util.spec_from_file_location(
        "core.utils.config_utils", ROOT / "core/utils/config_utils.py"
    )
    config = importlib.util.module_from_spec(config_spec)
    config_spec.loader.exec_module(config)
    monkeypatch.setitem(sys.modules, "core.utils.config_utils", config)
    monkeypatch.setitem(sys.modules, "core.utils.llm_api", api)
    path = tmp_path / "config.yaml"
    path.write_text(
        f"api:\n  protocol: cc_switch\n  cc_switch_url: {endpoint[0]}\n"
        "  key: ''\n  base_url: https://unused.invalid\n"
        "  model: claude-sonnet-5-5\n  llm_support_json: false\n", encoding="utf-8"
    )
    config.CONFIG_PATH = str(path)
    ask_spec = importlib.util.spec_from_file_location(
        "ask_gpt_under_test", ROOT / "core/utils/ask_gpt.py"
    )
    module = importlib.util.module_from_spec(ask_spec)
    ask_spec.loader.exec_module(module)
    module.GPT_LOG_FOLDER = str(tmp_path / "gpt_log")
    return module, config


def test_ask_gpt_cc_switch_needs_no_real_key_and_records_usage(ask, endpoint):
    module, _ = ask
    assert module.ask_gpt("Test", resp_type="json") == {"message": "success"}
    rows = json.loads((Path(module.GPT_LOG_FOLDER) / "default.json").read_text(encoding="utf-8"))
    assert rows[0]["usage"]["cache_creation_input_tokens"] == 512
    assert rows[0]["protocol"] == "cc_switch"
    module.ask_gpt("Test", resp_type="json")
    assert len(endpoint[1]["requests"]) == 1


def test_connection_check_bypasses_local_answer_cache(ask, endpoint):
    module, _ = ask
    module.ask_gpt("Test", resp_type="json")
    endpoint[1]["response"]["content"] = [{"type": "text", "text": '{"message":"changed"}'}]
    assert module.ask_gpt("Test", resp_type="json", use_cache=False) == {"message": "changed"}
    assert len(endpoint[1]["requests"]) == 2


def test_truncation_is_logged_without_repeated_paid_requests(ask, endpoint):
    module, _ = ask
    endpoint[1]["response"]["stop_reason"] = "max_tokens"
    with pytest.raises(ValueError, match="max_tokens"):
        module.ask_gpt("Test", resp_type="json")
    assert len(endpoint[1]["requests"]) == 1
    rows = json.loads((Path(module.GPT_LOG_FOLDER) / "error.json").read_text(encoding="utf-8"))
    assert rows[0]["stop_reason"] == "max_tokens"
    assert rows[0]["usage"]["output_tokens"] == 30


def test_old_config_without_protocol_keeps_openai_path(ask, endpoint):
    module, config = ask
    Path(config.CONFIG_PATH).write_text(
        f"api:\n  key: test-key\n  base_url: {endpoint[0]}\n"
        "  model: test-model\n  llm_support_json: true\n", encoding="utf-8"
    )
    endpoint[1]["response"] = {
        "id": "test-response", "object": "chat.completion", "created": 0,
        "model": "test-model", "choices": [{"index": 0, "finish_reason": "stop",
        "message": {"role": "assistant", "content": '{"message":"success"}'}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    }
    assert module.ask_gpt("Test", resp_type="json") == {"message": "success"}
    path, headers, body = endpoint[1]["requests"][0]
    assert path == "/v1/chat/completions"
    assert {key.lower(): value for key, value in headers.items()}["authorization"] == "Bearer test-key"
    assert body["response_format"] == {"type": "json_object"}


def test_sidebar_switches_protocol_without_overwriting_direct_credentials(ask, monkeypatch, tmp_path):
    from streamlit.testing.v1 import AppTest

    module, config = ask
    Path(config.CONFIG_PATH).write_text(
        "api:\n  protocol: cc_switch\n  key: test-direct-key\n"
        "  base_url: https://direct.invalid\n  model: claude-sonnet-5-5\n"
        "  cc_switch_model: videolingo-default\n"
        "  llm_support_json: false\n"
        "whisper:\n  language: en\n  runtime: local\n"
        "target_language: Chinese\ndemucs: false\nburn_subtitles: false\n"
        "tts_method: edge_tts\nedge_tts:\n  voice: en-US-JennyNeural\n",
        encoding="utf-8",
    )
    utils = sys.modules["core.utils"]
    utils.load_key = config.load_key
    utils.load_key_or = config.load_key_or
    utils.update_key = config.update_key
    utils.ask_gpt = module.ask_gpt
    utils.__all__ = ["load_key", "load_key_or", "update_key", "ask_gpt"]
    ytdlp = types.ModuleType("core._1_ytdlp")
    ytdlp.is_audio_only_input = lambda: False
    monkeypatch.setitem(sys.modules, "core._1_ytdlp", ytdlp)
    spec = importlib.util.spec_from_file_location(
        "sidebar_under_test", ROOT / "core/st_utils/sidebar_setting.py"
    )
    sidebar = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sidebar)
    monkeypatch.setitem(sys.modules, "sidebar_under_test", sidebar)
    app = AppTest.from_string("from sidebar_under_test import page_setting\npage_setting()", default_timeout=15)
    app.run()
    assert not app.exception
    assert app.selectbox[0].value == "cc_switch"
    assert "API_KEY" not in [field.label for field in app.text_input]
    assert not app.number_input
    logical = next(field for field in app.selectbox if field.key == "cc_switch_model")
    assert logical.options == ["opus", "sonnet", "haiku"]
    assert logical.value == "sonnet"
    assert config.load_key("api.cc_switch_model") == "sonnet"
    for model in ("opus", "haiku", "sonnet"):
        logical = next(field for field in app.selectbox if field.key == "cc_switch_model")
        logical.select(model).run()
        assert not app.exception
        assert config.load_key("api.cc_switch_model") == model
    reasoning = next(field for field in app.selectbox if field.key == "reasoning_cc_switch")
    assert reasoning.options == ["Auto / Default", "Low", "Medium", "High", "Very High", "Maximum"]
    reasoning.select("xhigh").run()
    assert config.load_key("api.cc_switch_reasoning") == "xhigh"
    reasoning = next(field for field in app.selectbox if field.key == "reasoning_cc_switch")
    reasoning.select("maximum").run()
    assert config.load_key("api.cc_switch_model") == "sonnet"
    assert config.load_key("api.cc_switch_reasoning") == "maximum"
    assert config.load_key("api.model") == "claude-sonnet-5-5"
    app.selectbox[0].select("openai").run()
    assert not app.exception
    assert config.load_key("api.protocol") == "openai"
    assert config.load_key("api.key") == "test-direct-key"
    assert config.load_key("api.base_url") == "https://direct.invalid"
    config.update_key("api.model", "mimo-v2.5-pro")
    app = AppTest.from_string("from sidebar_under_test import page_setting\npage_setting()").run()
    assert not app.exception
    reasoning = next(field for field in app.selectbox if field.key == "reasoning_mimo")
    assert reasoning.options == ["Model default", "Thinking off", "Thinking on"]
    reasoning.select("off").run()
    assert config.load_key("api.reasoning_effort_mimo") == "off"


def test_local_cache_isolated_between_models_and_reasoning_choices(ask, endpoint):
    module, config = ask
    module.ask_gpt("Test", resp_type="json")
    config.update_key("api.cc_switch_reasoning", "high", create=True)
    module.ask_gpt("Test", resp_type="json")
    assert len(endpoint[1]["requests"]) == 2
    config.update_key("api.model", "mimo-v2.5-pro")
    module.ask_gpt("Test", resp_type="json")
    assert len(endpoint[1]["requests"]) == 3


def test_high_very_high_and_maximum_have_separate_cache_identities(ask, endpoint):
    module, config = ask
    for count, level in enumerate(("high", "xhigh", "maximum"), 1):
        config.update_key("api.cc_switch_reasoning", level, create=True)
        endpoint[1]["response"]["content"] = [{"type": "text", "text": json.dumps({"level": level})}]
        assert module.ask_gpt("Identical prompt", resp_type="json") == {"level": level}
        assert module.ask_gpt("Identical prompt", resp_type="json") == {"level": level}
        assert len(endpoint[1]["requests"]) == count
    for level in ("high", "xhigh", "maximum"):
        config.update_key("api.cc_switch_reasoning", level)
        assert module.ask_gpt("Identical prompt", resp_type="json") == {"level": level}
    assert len(endpoint[1]["requests"]) == 3
    rows = json.loads((Path(module.GPT_LOG_FOLDER) / "default.json").read_text(encoding="utf-8"))
    assert [row["request_context"]["reasoning_effort"] for row in rows] == ["high", "xhigh", "maximum"]


@pytest.mark.parametrize("model,protocol,levels", [
    ("gpt-5.5", "openai", ("default", "none", "low", "medium", "high", "xhigh")),
    ("gpt-5.1", "openai", ("default", "none", "low", "medium", "high")),
    ("gpt-5", "openai", ("default", "minimal", "low", "medium", "high")),
    ("gpt-4o", "openai", ("default",)),
    ("claude-sonnet-5-5", "anthropic", ("default", "low", "medium", "high", "xhigh", "max")),
    ("claude-sonnet-4-6", "anthropic", ("default", "low", "medium", "high", "max")),
    ("deepseek-v4-pro", "openai", ("default", "off", "low", "high", "max")),
    ("deepseek-flash", "openai", ("default", "off", "low", "high", "max")),
    ("deepseek-chat", "openai", ("default", "off", "on")),
    ("gemini-2.5-flash", "openai", ("default", "none", "low", "medium", "high")),
    ("gemini-2.5-pro", "openai", ("default", "low", "medium", "high")),
    ("gemini-3-pro-preview", "openai", ("default", "low", "high")),
    ("gemini-3-flash-preview", "openai", ("default", "minimal", "low", "medium", "high")),
    ("gemini-3.8-flash", "openai", ("default", "low", "medium", "high")),
    ("gemini-4-argon", "openai", ("default", "low", "medium", "high")),
    ("mimo-v2.6-pro", "openai", ("default", "off", "on")),
    ("xiaomi/mimo-v2.5-pro", "anthropic", ("default", "off", "on")),
])
def test_reasoning_levels_match_model_capabilities(api, model, protocol, levels):
    assert api.reasoning_profile(model, protocol)["levels"] == levels


@pytest.mark.parametrize("model,level,protocol,want", [
    ("gpt-5.5", "medium", "openai", {"reasoning_effort": "medium"}),
    ("gpt-5.5", "xhigh", "openai", {"reasoning_effort": "xhigh"}),
    ("gpt-5.5", "none", "openai", {"reasoning_effort": "none"}),
    ("claude-sonnet-5-5", "high", "anthropic", {"output_config": {"effort": "high"}}),
    ("claude-sonnet-5-5", "xhigh", "anthropic", {"output_config": {"effort": "xhigh"}}),
    ("gpt-5.5", "high", "cc_switch", {"thinking": {"type": "adaptive"}, "output_config": {"effort": "high"}}),
    ("deepseek-v4-pro", "low", "openai", {"reasoning_effort": "low", "extra_body": {"thinking": {"type": "enabled"}}}),
    ("deepseek-v4-pro", "off", "openai", {"extra_body": {"thinking": {"type": "disabled"}}}),
    ("deepseek-v4-pro", "max", "anthropic", {"thinking": {"type": "enabled"}, "output_config": {"effort": "max"}}),
    ("deepseek-chat", "on", "openai", {"extra_body": {"thinking": {"type": "enabled"}}}),
    ("gemini-2.5-flash", "none", "openai", {"reasoning_effort": "none"}),
    ("gemini-3-flash-preview", "medium", "openai", {"reasoning_effort": "medium"}),
    ("mimo-v2.5-pro", "off", "openai", {"extra_body": {"thinking": {"type": "disabled"}}}),
    ("mimo-v2.5-pro", "on", "anthropic", {"thinking": {"type": "enabled"}}),
])
def test_reasoning_parameters_use_provider_wire_format(api, model, level, protocol, want):
    assert api.reasoning_parameters(model, level, protocol, upstream_format="anthropic") == want


@pytest.mark.parametrize("model", ["gpt-5.5", "claude-sonnet-5-5", "deepseek-flash", "gemini-3-flash-preview", "mimo-v2.5-pro"])
def test_default_leaves_provider_reasoning_defaults_intact(api, model):
    assert api.reasoning_parameters(model, "default", "openai") == {}


@pytest.mark.parametrize("model,level", [("deepseek-flash", "medium"), ("mimo-v2.5-pro", "high"), ("gemini-3-pro-preview", "medium"), ("gpt-4o", "low")])
def test_unsupported_level_is_not_silently_sent_or_mapped(api, model, level):
    with pytest.raises(api.LLMResponseError, match="reasoning"):
        api.reasoning_parameters(model, level, "openai")


@pytest.mark.parametrize("model", ["claude-sonnet-5-5", "sonnet", "custom-logical-name"])
@pytest.mark.parametrize("upstream", ["anthropic", "openai_chat", "openai_responses", "gemini_native", "unknown"])
def test_cc_switch_logic_is_independent_of_model_name_and_provider(api, model, upstream):
    assert api.reasoning_profile(model, "cc_switch", upstream)["levels"] == api.CC_SWITCH_LEVELS
    assert api.reasoning_parameters(model, "default", "cc_switch", upstream_format=upstream) == {}
    for level in ("low", "medium", "high", "xhigh", "maximum"):
        assert api.reasoning_parameters(model, level, "cc_switch", upstream_format=upstream) == {
            "thinking": {"type": "adaptive"}, "output_config": {"effort": "max" if level == "maximum" else level}}


@pytest.mark.parametrize("level,wire", [("default", None), ("low", "low"), ("medium", "medium"),
                                      ("high", "high"), ("xhigh", "xhigh"), ("maximum", "max")])
@pytest.mark.parametrize("upstream", ["anthropic", "openai_responses", "gemini_native"])
def test_cc_switch_six_levels_reach_messages_as_intent_not_product_modes(api, endpoint, level, wire, upstream):
    api.request_anthropic("Test", model="claude-sonnet-5-5", base_url=endpoint[0],
                          api_key="", cc_switch=True, effort=level, upstream_format=upstream)
    path, _, body = endpoint[1]["requests"][0]
    assert path == "/v1/messages"
    if wire is None:
        assert "thinking" not in body and "output_config" not in body
    else:
        assert body["output_config"]["effort"] == wire
        assert body["thinking"] == {"type": "adaptive"}
    assert "ultra" not in json.dumps(body).lower()


@pytest.mark.parametrize("level", ["ultra", "extra", "extreme"])
def test_product_modes_are_not_cc_switch_reasoning_levels(api, endpoint, level):
    assert api.CC_SWITCH_LEVELS == ("default", "low", "medium", "high", "xhigh", "maximum")
    with pytest.raises(api.LLMResponseError, match="logical reasoning"):
        api.request_anthropic("Test", model="sonnet", base_url=endpoint[0], api_key="",
                              cc_switch=True, effort=level)
    assert not endpoint[1]["requests"]


def test_cc_switch_gpt_effort_includes_thinking_so_converter_keeps_high(api, endpoint):
    base, state = endpoint
    api.request_anthropic("Test", model="gpt-5.5", base_url=base,
                          api_key="", cc_switch=True, effort="high",
                          upstream_format="openai_chat")
    body = state["requests"][0][2]
    assert body["thinking"] == {"type": "adaptive"}
    assert body["output_config"] == {"effort": "high"}


def switch_route(api, provider):
    path = api.route_folder / "live-state.json"
    state = json.loads(path.read_text(encoding="utf-8"))
    state["apps"]["claude"]["proxy_route"] = provider
    path.write_text(json.dumps(state), encoding="utf-8")


def test_deepseek_role_selection_and_mapping_changes_isolate_cache(api, ask, endpoint):
    module, config = ask
    settings = {"env": {"ANTHROPIC_DEFAULT_SONNET_MODEL": "deepseek-v4-1-flash",
                        "ANTHROPIC_DEFAULT_OPUS_MODEL": "deepseek-v4-pro"}}
    with sqlite3.connect(api.route_folder / "cc-switch.db") as db:
        db.execute("INSERT INTO providers VALUES (?, 'claude', ?, ?, 0)",
                   ("deepseek-provider", json.dumps({"apiFormat": "anthropic"}), json.dumps(settings)))
    switch_route(api, "deepseek-provider")
    config.update_key("api.cc_switch_reasoning", "default", create=True)
    for role, actual in (("sonnet", "deepseek-v4-1-flash"), ("opus", "deepseek-v4-pro")):
        config.update_key("api.cc_switch_model", role, create=True)
        endpoint[1]["response"]["model"] = actual
        endpoint[1]["response"]["content"] = [{"type": "text", "text": json.dumps({"model": actual})}]
        assert module.ask_gpt("Translate Hello", resp_type="json") == {"model": actual}
        assert module.ask_gpt("Translate Hello", resp_type="json") == {"model": actual}
        body = endpoint[1]["requests"][-1][2]
        assert body["model"] == role
        assert "thinking" not in body and "output_config" not in body
    assert len(endpoint[1]["requests"]) == 2
    config.update_key("api.cc_switch_model", "sonnet")
    assert module.ask_gpt("Translate Hello", resp_type="json") == {"model": "deepseek-v4-1-flash"}
    assert len(endpoint[1]["requests"]) == 2
    config.update_key("api.cc_switch_model", "opus")
    with sqlite3.connect(api.route_folder / "cc-switch.db") as db:
        db.execute("UPDATE providers SET settings_config=json_set(settings_config, "
                   "'$.env.ANTHROPIC_DEFAULT_OPUS_MODEL', 'deepseek-new-pro') WHERE id='deepseek-provider'")
    module.ask_gpt("Translate Hello", resp_type="json")
    assert len(endpoint[1]["requests"]) == 3
    rows = json.loads((Path(module.GPT_LOG_FOLDER) / "default.json").read_text(encoding="utf-8"))
    assert [row["model"] for row in rows[:2]] == ["deepseek-v4-1-flash", "deepseek-v4-pro"]
    assert rows[1]["request_context"] != rows[2]["request_context"]


def test_provider_switch_and_mapping_change_invalidate_cache_without_restart(api, ask, endpoint):
    module, config = ask
    config.update_key("api.cc_switch_model", "claude-sonnet-5-5", create=True)
    config.update_key("api.cc_switch_reasoning", "maximum", create=True)
    for count, provider in enumerate(("claude-provider", "gpt-provider", "gemini-provider"), 1):
        switch_route(api, provider)
        endpoint[1]["response"]["content"] = [{"type": "text", "text": json.dumps({"provider": provider})}]
        assert module.ask_gpt("Translate Hello", resp_type="json") == {"provider": provider}
        assert module.ask_gpt("Translate Hello", resp_type="json") == {"provider": provider}
        assert len(endpoint[1]["requests"]) == count
    with sqlite3.connect(api.route_folder / "cc-switch.db") as db:
        db.execute("UPDATE providers SET settings_config=json_set(settings_config, '$.env.ANTHROPIC_DEFAULT_SONNET_MODEL', 'new-mapping') WHERE id='gemini-provider'")
    module.ask_gpt("Translate Hello", resp_type="json")
    module.ask_gpt("Translate Hello", resp_type="json")
    assert len(endpoint[1]["requests"]) == 4
    for path, headers, body in endpoint[1]["requests"]:
        assert path == "/v1/messages"
        assert headers["x-api-key"] == "cc-switch-proxy"
        assert body["model"] == "claude-sonnet-5-5"
        assert body["output_config"] == {"effort": "max"}
        assert body["thinking"] == {"type": "adaptive"}
    logs = (Path(module.GPT_LOG_FOLDER) / "default.json").read_text(encoding="utf-8")
    assert "credential-must-never-be-logged" not in logs
    contexts = [item["request_context"] for item in json.loads(logs)]
    assert len({json.dumps(c, sort_keys=True) for c in contexts}) == 4


def test_cc_switch_config_isolated_from_direct_and_missing_model_keeps_legacy_fallback(api, ask, endpoint):
    module, config = ask
    config.update_key("api.cc_switch_model", "sonnet", create=True)
    config.update_key("api.cc_switch_reasoning", "default", create=True)
    module.ask_gpt("Test")
    config.update_key("api.model", "gpt-direct-only")
    config.update_key("api.reasoning_effort_claude", "max", create=True)
    config.update_key("api.claude_effort", "high", create=True)
    config.update_key("api.reasoning_effort_gpt", "high", create=True)
    config.update_key("api.base_url", "https://do-not-send.invalid")
    config.update_key("api.key", "do-not-send-key")
    module.ask_gpt("Test")
    assert len(endpoint[1]["requests"]) == 1
    module.ask_gpt("New HTTP", use_cache=False)
    _, headers, body = endpoint[1]["requests"][-1]
    assert body["model"] == "sonnet"
    assert "thinking" not in body and "output_config" not in body
    assert "do-not-send-key" not in json.dumps(headers)
    assert api.configured_model(config.load_key_or, config.load_key, "openai") == "gpt-direct-only"
    assert api.configured_reasoning(config.load_key_or, "claude-sonnet-5-5", "anthropic") == "max"
    Path(config.CONFIG_PATH).write_text("api:\n  model: old-config-model\n", encoding="utf-8")
    assert api.configured_model(config.load_key_or, config.load_key, "cc_switch") == "old-config-model"
    assert api.configured_reasoning(config.load_key_or, "old-config-model", "cc_switch") == "default"


@pytest.mark.parametrize("uncertain", ["missing_state", "stack", "failover", "missing_provider", "malformed_meta"])
def test_unknown_or_failover_route_bypasses_answer_cache(api, ask, endpoint, uncertain):
    module, _ = ask
    module.ask_gpt("Test")
    if uncertain == "missing_state":
        (api.route_folder / "live-state.json").unlink()
    elif uncertain == "stack":
        (api.route_folder / "live-state.json").write_text('{"apps":{"claude":{"mode":"stack"}}}', encoding="utf-8")
    elif uncertain == "missing_provider":
        switch_route(api, "not-configured")
    else:
        with sqlite3.connect(api.route_folder / "cc-switch.db") as db:
            db.execute("UPDATE proxy_config SET auto_failover_enabled=1" if uncertain == "failover"
                       else "UPDATE providers SET meta='invalid-json'")
    assert api.cc_switch_route_identity() is None
    module.ask_gpt("Test")
    module.ask_gpt("Test")
    assert len(endpoint[1]["requests"]) == 3


def test_switch_during_http_does_not_save_answer_under_wrong_provider(api, ask, endpoint, monkeypatch):
    module, _ = ask
    request = module.request_anthropic
    def change_after_http(*args, **kwargs):
        result = request(*args, **kwargs)
        switch_route(api, "gpt-provider")
        return result
    monkeypatch.setattr(module, "request_anthropic", change_after_http)
    module.ask_gpt("Test")
    rows = json.loads((Path(module.GPT_LOG_FOLDER) / "default.json").read_text(encoding="utf-8"))
    assert rows[0]["request_context"] is None
    monkeypatch.setattr(module, "request_anthropic", request)
    module.ask_gpt("Test")
    module.ask_gpt("Test")
    assert len(endpoint[1]["requests"]) == 2


def test_mapping_fingerprint_is_stable_and_credentials_are_excluded(api):
    identity = api.cc_switch_route_identity()
    assert identity["app"] == "claude"
    assert identity["provider_id"] == "claude-provider"
    assert identity["api_format"] == "anthropic"
    assert len(identity["mapping_fingerprint"]) == 64
    with sqlite3.connect(api.route_folder / "cc-switch.db") as db:
        db.execute("UPDATE providers SET settings_config=json_set(settings_config, '$.env.ANTHROPIC_AUTH_TOKEN', 'rotated-secret', '$.env.ANTHROPIC_BASE_URL', 'https://new.invalid') WHERE id='claude-provider'")
    assert api.cc_switch_route_identity() == identity
    with sqlite3.connect(api.route_folder / "cc-switch.db") as db:
        db.execute("UPDATE providers SET meta=json_set(meta, '$.apiFormat', 'openai_responses') WHERE id='claude-provider'")
    assert api.cc_switch_route_identity() != identity
    identity = api.cc_switch_route_identity()
    with sqlite3.connect(api.route_folder / "cc-switch.db") as db:
        db.execute("UPDATE providers SET meta=json_set(meta, '$.isFullUrl', 1) WHERE id='claude-provider'")
    assert api.cc_switch_route_identity() != identity


@pytest.mark.parametrize("model,level,want", [
    ("deepseek-flash", "max", {"thinking": {"type": "enabled"}, "output_config": {"effort": "max"}}),
    ("mimo-v2.5-pro", "off", {"thinking": {"type": "disabled"}}),
])
def test_native_non_claude_reasoning_reaches_http_payload(api, endpoint, model, level, want):
    base, state = endpoint
    api.request_anthropic("Test", model=model, base_url=base, api_key="test-key", effort=level)
    body = state["requests"][0][2]
    for key, value in want.items():
        assert body[key] == value


def test_openai_gemini_base_path_is_not_rewritten_to_v1(ask, endpoint):
    module, config = ask
    Path(config.CONFIG_PATH).write_text(
        f"api:\n  protocol: openai\n  key: test-key\n  base_url: {endpoint[0]}/v1beta/openai/\n"
        "  model: gemini-3-flash-preview\n  llm_support_json: false\n  reasoning_effort_gemini: medium\n",
        encoding="utf-8",
    )
    endpoint[1]["response"] = {
        "id": "response", "object": "chat.completion", "created": 0,
        "model": "gemini-3-flash-preview", "choices": [{"index": 0, "finish_reason": "stop",
        "message": {"role": "assistant", "content": '{"message":"success"}'}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    }
    module.ask_gpt("Test", resp_type="json")
    path, _, body = endpoint[1]["requests"][0]
    assert path == "/v1beta/openai/chat/completions"
    assert body["reasoning_effort"] == "medium"


@pytest.mark.parametrize("model,setting,want", [
    ("gpt-5.5", "high", {"reasoning_effort": "high"}),
    ("deepseek-flash", "low", {"reasoning_effort": "low", "thinking": {"type": "enabled"}}),
    ("mimo-v2.5-pro", "off", {"thinking": {"type": "disabled"}}),
])
def test_openai_reasoning_reaches_http_payload(ask, endpoint, model, setting, want):
    module, config = ask
    family = model.split("-")[0]
    Path(config.CONFIG_PATH).write_text(
        f"api:\n  protocol: openai\n  key: test-key\n  base_url: {endpoint[0]}\n"
        f"  model: {model}\n  llm_support_json: false\n  reasoning_effort_{family}: {setting}\n",
        encoding="utf-8",
    )
    endpoint[1]["response"] = {
        "id": "response", "object": "chat.completion", "created": 0,
        "model": model, "choices": [{"index": 0, "finish_reason": "stop",
        "message": {"role": "assistant", "content": '{"message":"success"}'}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    }
    module.ask_gpt("Test", resp_type="json")
    body = endpoint[1]["requests"][0][2]
    for key, value in want.items():
        assert body[key] == value


def test_mimo_direct_endpoint_uses_official_api_key_header(api):
    assert api.openai_headers("https://api.xiaomimimo.com/v1", "test-key") == {"api-key": "test-key"}
    assert api.openai_headers("https://relay.example/v1", "test-key") == {}
