import os
import json
from threading import Lock
import json_repair
from openai import OpenAI
from core.utils.config_utils import load_key, load_key_or
from core.utils.llm_api import (CC_SWITCH_URL, LLMResponseError, request_anthropic,
                                configured_model, configured_reasoning, reasoning_parameters,
                                cc_switch_route_identity, openai_base_url, openai_headers)
from rich import print as rprint
from core.utils.decorator import except_handler

# ------------
# cache gpt response
# ------------

LOCK = Lock()
GPT_LOG_FOLDER = 'output/gpt_log'

def _save_cache(model, prompt, resp_content, resp_type, resp, message=None, log_title="default", metadata=None):
    with LOCK:
        logs = []
        file = os.path.join(GPT_LOG_FOLDER, f"{log_title}.json")
        os.makedirs(os.path.dirname(file), exist_ok=True)
        if os.path.exists(file):
            with open(file, 'r', encoding='utf-8') as f:
                logs = json.load(f)
        item = {"model": model, "prompt": prompt, "resp_content": resp_content, "resp_type": resp_type, "resp": resp, "message": message}
        if metadata:
            item.update(metadata)
        logs.append(item)
        with open(file, 'w', encoding='utf-8') as f:
            json.dump(logs, f, ensure_ascii=False, indent=4)

def _load_cache(prompt, resp_type, log_title, request_context=None):
    with LOCK:
        file = os.path.join(GPT_LOG_FOLDER, f"{log_title}.json")
        if os.path.exists(file):
            with open(file, 'r', encoding='utf-8') as f:
                for item in json.load(f):
                    if (item["prompt"] == prompt and item["resp_type"] == resp_type
                            and (request_context is None or item.get("request_context") == request_context)):
                        return item["resp"]
        return False

# ------------
# ask gpt once
# ------------

@except_handler("GPT request failed", retry=5, no_retry=(LLMResponseError,))
def ask_gpt(prompt, resp_type=None, valid_def=None, log_title="default", use_cache=True):
    protocol = load_key_or("api.protocol", "openai")
    if protocol not in ("openai", "anthropic", "cc_switch"):
        raise LLMResponseError(f"Unsupported API protocol: {protocol}")
    if protocol != "cc_switch" and not load_key("api.key"):
        raise ValueError("API key is not set")
    model = configured_model(load_key_or, load_key, protocol)
    effort = configured_reasoning(load_key_or, model, protocol)
    context = {"model": model, "protocol": protocol, "reasoning_effort": effort}
    route = None
    if protocol == "cc_switch":
        route = cc_switch_route_identity()
        context.update(cc_switch_route=route,
                       cc_switch_url=load_key_or("api.cc_switch_url", CC_SWITCH_URL))
    cache_allowed = protocol != "cc_switch" or route is not None
    cached = _load_cache(prompt, resp_type, log_title, context) if use_cache and cache_allowed else False
    if cached and protocol == "cc_switch" and cc_switch_route_identity() != route:
        cached = False
    if cached:
        rprint("use cache response")
        return cached

    metadata = None
    if protocol in ("anthropic", "cc_switch"):
        try:
            resp_content, metadata = request_anthropic(
                prompt, model=model,
                base_url=context["cc_switch_url"] if protocol == "cc_switch" else load_key("api.base_url"),
                api_key="" if protocol == "cc_switch" else load_key("api.key"),
                cc_switch=protocol == "cc_switch",
                effort=effort,
                max_tokens=load_key_or("api.claude_max_tokens", 8192),
                prompt_cache=load_key_or("api.prompt_cache", True),
            )
        except LLMResponseError as exc:
            _save_cache(model, prompt, exc.content, resp_type, None,
                        log_title="error", message=str(exc),
                        metadata={**exc.metadata, "request_context": context})
            raise
    else:
        base_url = openai_base_url(load_key("api.base_url"))
        client = OpenAI(api_key=load_key("api.key"), base_url=base_url,
                        default_headers=openai_headers(base_url, load_key("api.key")))
        response_format = {"type": "json_object"} if resp_type == "json" and load_key("api.llm_support_json") else None
        resp_raw = client.chat.completions.create(
            model=model, messages=[{"role": "user", "content": prompt}],
            response_format=response_format, timeout=300,
            **reasoning_parameters(model, effort, "openai"),
        )
        resp_content = resp_raw.choices[0].message.content
        metadata = {"protocol": "openai", "usage": resp_raw.usage.model_dump() if resp_raw.usage else {},
                    "stop_reason": resp_raw.choices[0].finish_reason}
    # A switch during an in-flight request makes the actual provider uncertain.
    # Keep the log, but do not make its answer eligible for future cache hits.
    if protocol == "cc_switch" and (not cache_allowed or cc_switch_route_identity() != route):
        context = None
    metadata.update(reasoning_effort=effort, request_context=context)
    if resp_type == "json":
        resp = json_repair.loads(resp_content)
    else:
        resp = resp_content
    
    # check if the response format is valid
    if valid_def:
        valid_resp = valid_def(resp)
        if valid_resp['status'] != 'success':
            _save_cache(model, prompt, resp_content, resp_type, resp, log_title="error", message=valid_resp['message'], metadata=metadata)
            raise ValueError(f"❎ API response error: {valid_resp['message']}")

    _save_cache(model, prompt, resp_content, resp_type, resp, log_title=log_title, metadata=metadata)
    return resp


if __name__ == '__main__':
    from rich import print as rprint
    
    result = ask_gpt("""test respond ```json\n{\"code\": 200, \"message\": \"success\"}\n```""", resp_type="json")
    rprint(f"Test json output result: {result}")
