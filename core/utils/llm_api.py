"""Model-specific reasoning controls and Claude/CC Switch Messages transport."""
import re
import json
import sqlite3
import hashlib
from pathlib import Path
from contextlib import closing
from urllib.parse import urlsplit

import requests


CC_SWITCH_URL = "http://127.0.0.1:15721"
CC_SWITCH_LEVELS = ("default", "low", "medium", "high", "xhigh", "maximum")
# Only model mapping fields are selected from settings_config. Never select credentials.
CC_SWITCH_MAPPING_KEYS = ("ANTHROPIC_MODEL", "ANTHROPIC_DEFAULT_HAIKU_MODEL",
                          "ANTHROPIC_DEFAULT_SONNET_MODEL", "ANTHROPIC_DEFAULT_OPUS_MODEL",
                          "ANTHROPIC_DEFAULT_FABLE_MODEL", "CLAUDE_CODE_SUBAGENT_MODEL")


class LLMResponseError(ValueError):
    """A request that should not be repeated unchanged (and billed again)."""

    def __init__(self, message, *, content="", metadata=None):
        super().__init__(message)
        self.content = content
        self.metadata = metadata or {}


def cc_switch_route_identity(folder=None):
    """Fresh, credential-free identity; uncertain/failover routes cannot use answer cache."""
    folder = Path(folder) if folder is not None else Path.home() / ".cc-switch"
    try:
        state = json.loads((folder / "live-state.json").read_text(encoding="utf-8"))
        app = state.get("apps", {}).get("claude", {})
        if app.get("mode") != "proxy":
            return None
        route = app.get("proxy_route")
        with closing(sqlite3.connect((folder / "cc-switch.db").as_uri() + "?mode=ro", uri=True)) as db:
            proxy = db.execute("SELECT enabled, auto_failover_enabled FROM proxy_config WHERE app_type='claude'").fetchone()
            if not proxy or not proxy[0] or proxy[1]:
                return None
            fields = ", ".join("json_extract(settings_config, '$.env." + key + "')"
                               for key in CC_SWITCH_MAPPING_KEYS)
            query = ("SELECT id, COALESCE(json_extract(meta, '$.apiFormat'), 'anthropic'), "
                     "COALESCE(json_extract(meta, '$.isFullUrl'), 0), " + fields +
                     " FROM providers WHERE app_type='claude' AND ")
            if route:
                rows = db.execute(query + "id=?", (route,)).fetchall()
            else:
                rows = db.execute(query + "is_current=1").fetchall()
        if len(rows) != 1:
            return None
        latest = json.loads((folder / "live-state.json").read_text(encoding="utf-8"))
        if latest.get("apps", {}).get("claude", {}) != app:
            return None
        row = rows[0]
        mapping = dict(zip(CC_SWITCH_MAPPING_KEYS, row[3:]))
        canonical = json.dumps(mapping, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return {"app": "claude", "provider_id": row[0], "api_format": row[1],
                "is_full_url": bool(row[2]),
                "mapping_fingerprint": hashlib.sha256(canonical.encode("utf-8")).hexdigest()}
    except (OSError, ValueError, sqlite3.Error, TypeError, AttributeError):
        return None


def cc_switch_upstream_format():
    identity = cc_switch_route_identity()
    return identity["api_format"] if identity else "unknown"


def configured_model(load_optional, load_required, protocol):
    if protocol == "cc_switch":
        model = load_optional("api.cc_switch_model", None)
        if model is not None:
            return model
    return load_required("api.model")


def reasoning_profile(model, protocol="openai", upstream_format=None):
    """Expose real model capabilities, narrowed by the request path's capabilities."""
    if protocol == "cc_switch":
        return {"family": "cc_switch", "mode": "logical", "levels": CC_SWITCH_LEVELS,
                "note": ""}
    name = model.lower().rsplit("/", 1)[-1]
    family, mode, levels = "other", "unsupported", ("default",)
    if name.startswith("gpt-") or re.match(r"o[134](?:-|$)", name):
        family = "gpt"
        version = re.match(r"gpt-(\d+)(?:\.(\d+))?", name)
        if re.match(r"o[134](?:-|$)", name) and not any(x in name for x in ("o1-mini", "o1-preview")):
            mode, levels = "effort", ("default", "low", "medium", "high")
        elif version and int(version[1]) >= 5 and "chat" not in name:
            mode = "effort"
            major, minor = int(version[1]), int(version[2] or 0)
            levels = ("default", "minimal", "low", "medium", "high")
            if major == 5 and minor >= 1:
                levels = ("default", "none", "low", "medium", "high")
            if minor >= 2 or major >= 6:
                levels += ("xhigh",)
            if major >= 6:
                levels = ("default", "low", "medium", "high", "xhigh")
            if "-pro" in name:
                levels = ("default", "high") if minor == 0 and major == 5 else ("default", "medium", "high", "xhigh")
    elif name.startswith("claude-"):
        family = "claude"
        version = re.search(r"claude-(sonnet|opus|haiku)-(\d+)(?:[-.](\d{1,2})(?=[-.]|$))?", name)
        if version:
            kind, major, minor = version[1], int(version[2]), int(version[3] or 0)
            if major >= 5 or (major == 4 and minor >= 6) or (kind == "opus" and major == 4 and minor == 5):
                mode, levels = "effort", ("default", "low", "medium", "high")
                if major >= 5 or (kind == "opus" and major == 4 and minor >= 7):
                    levels += ("xhigh", "max")
                elif (kind in ("opus", "sonnet") and major == 4 and minor >= 6):
                    levels += ("max",)
            elif (kind == "sonnet" and (major == 4 or (major == 3 and minor == 7))) or (kind == "haiku" and major == 4 and minor == 5):
                mode, levels = "legacy_claude", ("default", "off", "low", "medium", "high")
    elif name.startswith("deepseek"):
        family = "deepseek"
        if re.search(r"deepseek-(?:v[4-9]|flash|pro)", name):
            mode, levels = "deepseek_effort", ("default", "off", "low", "high", "max")
        elif name.startswith("deepseek-chat") or re.search(r"deepseek-v3[.-][12]", name):
            mode, levels = "toggle", ("default", "off", "on")
    elif name.startswith("gemini-") and not any(x in name for x in ("image", "tts", "embedding")):
        family = "gemini"
        version = re.match(r"gemini-(\d+)(?:\.(\d+))?", name)
        if version:
            major, minor = int(version[1]), int(version[2] or 0)
            if major == 2 and minor == 5:
                mode, levels = "effort", ("default", "low", "medium", "high")
                if "pro" not in name:
                    levels = ("default", "none", "low", "medium", "high")
            elif major >= 3:
                mode, levels = "effort", ("default", "low", "medium", "high")
                if major == 3 and "pro" in name:
                    levels = ("default", "low", "high")
                elif major == 3 and "flash" in name and minor < 8:
                    levels = ("default", "minimal", "low", "medium", "high")
    elif name.startswith("mimo-") and not any(x in name for x in ("tts", "asr")):
        family, mode, levels = "mimo", "toggle", ("default", "off", "on")

    note = ""
    if protocol == "openai" and family == "claude":
        levels, note = ("default",), "Use Claude Messages API to control Claude reasoning."
    elif protocol == "anthropic" and family == "gemini":
        levels, note = ("default",), "Use OpenAI Compatible for Gemini reasoning; Anthropic has no standard Gemini thinking control."
    elif protocol == "anthropic" and family == "gpt":
        levels = tuple(level for level in levels if level not in ("none", "minimal"))
    return {"family": family, "mode": mode, "levels": levels, "note": note}


def configured_reasoning(load_optional, model, protocol, upstream_format=None):
    if protocol == "cc_switch":
        value = load_optional("api.cc_switch_reasoning", "default")
        return value if value in CC_SWITCH_LEVELS else "default"
    profile = reasoning_profile(model, protocol, upstream_format)
    fallback = load_optional("api.claude_effort", "low") if profile["family"] == "claude" else "default"
    value = load_optional("api.reasoning_effort_" + profile["family"], fallback)
    return value if value in profile["levels"] else "default"


def reasoning_parameters(model, effort, protocol, *, max_tokens=8192, upstream_format=None):
    if effort == "default":
        return {}
    if protocol == "cc_switch":
        if effort not in CC_SWITCH_LEVELS:
            raise LLMResponseError(f"Unsupported CC Switch logical reasoning level: {effort!r}")
        # Anthropic intent, independent of the logical model or upstream brand.
        # Maximum always means API max, never a product-level Ultra mode.
        # CC Switch converts max for GPT; Gemini Native safely omits these fields in 4.0.9.
        return {"thinking": {"type": "adaptive"},
                "output_config": {"effort": "max" if effort == "maximum" else effort}}
    profile = reasoning_profile(model, protocol, upstream_format)
    if effort not in profile["levels"]:
        raise LLMResponseError(profile["note"] or f"Unsupported reasoning level {effort!r} for {model}")
    family, mode = profile["family"], profile["mode"]
    native = protocol != "openai"
    if mode == "legacy_claude":
        thinking = {"type": "disabled"} if effort == "off" else {
            "type": "enabled", "budget_tokens": {"low": 1024, "medium": 2048, "high": 4096}[effort]}
        if effort != "off" and thinking["budget_tokens"] >= max_tokens:
            raise LLMResponseError("Claude reasoning budget must be below the output limit")
        return {"thinking": thinking}
    if mode == "toggle" or (family == "deepseek" and effort == "off"):
        thinking = {"type": "disabled" if effort == "off" else "enabled"}
        return {"thinking": thinking} if native else {"extra_body": {"thinking": thinking}}
    if mode == "deepseek_effort":
        if native:
            return {"thinking": {"type": "enabled"}, "output_config": {"effort": effort}}
        return {"reasoning_effort": effort, "extra_body": {"thinking": {"type": "enabled"}}}
    if native:
        parameters = {"output_config": {"effort": effort}}
        if family == "gpt":
            # Preserve explicit thinking intent on Anthropic-compatible GPT endpoints.
            parameters["thinking"] = {"type": "adaptive"}
        return parameters
    return {"reasoning_effort": effort}


def openai_base_url(base_url):
    url = base_url.rstrip("/")
    if "ark" in url:
        return "https://ark.cn-beijing.volces.com/api/v3"
    # Preserve Gemini's /v1beta/openai and other SDK-specific prefixes.
    if not urlsplit(url).path.rstrip("/"):
        url += "/v1"
    return url


def openai_headers(base_url, api_key):
    # MiMo's official API uses api-key; intermediaries use normal SDK auth.
    return {"api-key": api_key} if urlsplit(base_url).hostname == "api.xiaomimimo.com" else {}


def request_anthropic(prompt, *, model, base_url, api_key, cc_switch=False,
                      effort=None, max_tokens=8192, prompt_cache=True, upstream_format=None):
    if effort is None:
        effort = "default" if cc_switch else "low"
    url = base_url.rstrip("/")
    if cc_switch:
        parsed = urlsplit(url)
        # This mode must stay on Claude Code's local route, never Desktop's.
        if (parsed.scheme != "http" or parsed.hostname not in ("127.0.0.1", "localhost", "::1")
                or parsed.path not in ("", "/v1", "/v1/messages")
                or parsed.query or parsed.fragment or parsed.username):
            raise LLMResponseError("CC Switch must use its local Claude Code address, e.g. " + CC_SWITCH_URL)
        api_key = "cc-switch-proxy"
    elif not api_key:
        raise LLMResponseError("API key is not set")
    if not url:
        raise LLMResponseError("API base URL is not set")
    if not url.endswith("/v1/messages"):
        url += "/messages" if url.endswith("/v1") else "/v1/messages"
    if not isinstance(max_tokens, int) or isinstance(max_tokens, bool) or max_tokens <= 0:
        raise LLMResponseError("Claude max_tokens must be a positive integer")

    body = {"model": model, "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}]}
    # Cache only the stable instructions before any per-subtitle content.
    # Below the model's minimum prefix length, Anthropic skips caching.
    boundary = re.search(r"\n(?:### Context Information|## INPUT|## Given Text)\b", prompt)
    if boundary and prompt[:boundary.start()].strip():
        prefix = {"type": "text", "text": prompt[:boundary.start()]}
        if prompt_cache and (cc_switch or model.lower().rsplit("/", 1)[-1].startswith("claude-")):
            prefix["cache_control"] = {"type": "ephemeral"}
        body["system"] = [prefix]
        body["messages"][0]["content"] = prompt[boundary.start():]
    body.update(reasoning_parameters(model, effort, "cc_switch" if cc_switch else "anthropic",
                                     max_tokens=max_tokens, upstream_format=upstream_format))

    with requests.Session() as session:
        if cc_switch:
            session.trust_env = False
        try:
            response = session.post(url, headers={
                "api-key" if urlsplit(url).hostname == "api.xiaomimimo.com" else "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
            }, json=body, timeout=300, allow_redirects=False)
        except requests.ConnectionError as exc:
            if cc_switch:
                raise LLMResponseError(
                    "CC Switch local routing is unavailable. Start local routing for Claude Code in CC Switch."
                ) from exc
            raise
        if 300 <= response.status_code < 500 and response.status_code not in (408, 429):
            try:
                message = response.json().get("error", {}).get("message", "")
            except (ValueError, AttributeError):
                message = ""
            raise LLMResponseError(f"Claude API HTTP {response.status_code}: {message}")
        response.raise_for_status()
        raw = response.json()

    metadata = {"protocol": "cc_switch" if cc_switch else "anthropic",
                "model": raw.get("model", model), "usage": raw.get("usage", {}),
                "stop_reason": raw.get("stop_reason")}
    content = "".join(block.get("text", "") for block in raw.get("content", [])
                      if block.get("type") == "text")
    if raw.get("stop_reason") in ("max_tokens", "refusal"):
        raise LLMResponseError(
            f"Claude stopped with {raw['stop_reason']}; lower effort or review the output limit before retrying.",
            content=content, metadata=metadata,
        )
    if not content.strip():
        raise LLMResponseError("Claude returned no answer text", content=content, metadata=metadata)
    return content, metadata
