import streamlit as st
import requests
from translations.translations import translate as t
from core.utils import *
from core.utils.llm_api import (CC_SWITCH_URL, reasoning_profile, configured_reasoning,
                                configured_model, openai_base_url, openai_headers)


def config_input(label, key, help=None, placeholder=None, default=None):
    """Generic config input handler"""
    current = load_key_or(key, default) if default is not None else load_key(key)
    val = st.text_input(label, value=current, help=help, placeholder=placeholder)
    if val != current:
        update_key(key, val, create=default is not None)
    return val


def _fetch_model_list(base_url, api_key, protocol="openai"):
    """Fetch available models from OpenAI-compatible /v1/models endpoint."""
    if protocol == "cc_switch" or not api_key or not base_url:
        return []
    url = openai_base_url(base_url)
    url += "/models"
    try:
        headers = ({"x-api-key": api_key, "anthropic-version": "2023-06-01"}
                   if protocol == "anthropic" else {"Authorization": f"Bearer {api_key}"})
        headers.update(openai_headers(base_url, api_key))
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        data = resp.json().get("data", [])
        return sorted([m["id"] for m in data if "id" in m])
    except Exception:
        return []


def _search_models(search_term, **kwargs):
    """Search function for st_searchbox — returns models matching the search term."""
    models = st.session_state.get("_model_list", [])
    if not search_term:
        return models if models else []
    term = search_term.lower()
    matched = [m for m in models if term in m.lower()]
    # Always include the raw input as an option so users can type custom model names
    if search_term not in matched:
        matched.insert(0, search_term)
    return matched


def page_setting():
    # Widen the sidebar slightly to accommodate the model searchbox
    st.markdown(
        """<style>[data-testid="stSidebar"] {min-width: 420px; max-width: 420px;}</style>""",
        unsafe_allow_html=True,
    )

    # with st.expander(t("Youtube Settings"), expanded=True):
    #     config_input(t("Cookies Path"), "youtube.cookies_path")

    with st.expander(t("LLM Configuration"), expanded=True):
        protocols = ["openai", "anthropic", "cc_switch"]
        current_protocol = load_key_or("api.protocol", "openai")
        protocol = st.selectbox(
            t("API Connection"), protocols,
            index=protocols.index(current_protocol) if current_protocol in protocols else 0,
            format_func=lambda value: {"openai": "OpenAI Compatible",
                                      "anthropic": "Claude Messages API",
                                      "cc_switch": "CC Switch · Claude Code"}[value],
        )
        if protocol != current_protocol:
            update_key("api.protocol", protocol, create=True)
            st.session_state.pop("_model_list", None)
            st.session_state.pop("model_searchbox", None)
            st.rerun()

        if protocol == "cc_switch":
            config_input(t("CC Switch Local URL"), "api.cc_switch_url", default=CC_SWITCH_URL)
            st.caption(t("Manage the provider and API key in CC Switch's Claude Code page and start local routing. Claude Desktop uses its own provider."))
        else:
            config_input(t("API_KEY"), "api.key", placeholder=t("Enter your API key"))
            config_input(
                t("BASE_URL"), "api.base_url",
                help=t("Native Claude Messages API; appends /v1/messages automatically")
                if protocol == "anthropic" else t("Openai format, will add /v1/chat/completions automatically"),
            )

        # Try to use searchbox for model selection, fall back to text_input
        model_key = "api.cc_switch_model" if protocol == "cc_switch" else "api.model"
        current_model = configured_model(load_key_or, load_key, protocol)
        if protocol == "cc_switch":
            routing_models = ["opus", "sonnet", "haiku"]
            selected_model = st.selectbox(
                t("Logical Routing Model"), routing_models,
                index=routing_models.index(current_model) if current_model in routing_models else 1,
                key="cc_switch_model",
                help=t("CC Switch maps this logical model to the active provider's model."),
            )
            if selected_model != current_model:
                update_key(model_key, selected_model, create=True)
            if st.button("📡 " + t("Check API"), key="api", use_container_width=True):
                with st.spinner(t("Check API") + "..."):
                    is_valid = check_api()
                st.toast(t("API Key is valid") if is_valid else t("API Key is invalid"),
                         icon="✅" if is_valid else "❌")
        else:
            try:
                from streamlit_searchbox import st_searchbox
                from streamlit_searchbox import _list_to_options_js, _list_to_options_py

                if st.button(
                    t("Fetch Model List"), key="fetch_models", use_container_width=True,
                    disabled=protocol == "cc_switch",
                ):
                    with st.spinner(t("Fetching models...")):
                        models = _fetch_model_list(
                            load_key("api.base_url"), load_key("api.key"), protocol
                        )
                        st.session_state["_model_list"] = models
                        if models:
                            # Update searchbox internal state directly so dropdown shows options
                            sb_key = "model_searchbox"
                            if sb_key in st.session_state:
                                st.session_state[sb_key]["options_js"] = (
                                    _list_to_options_js(models)
                                )
                                st.session_state[sb_key]["options_py"] = (
                                    _list_to_options_py(models)
                                )
                            st.toast(
                                t("Fetched {n} models").replace("{n}", str(len(models))),
                                icon="✅",
                            )
                        else:
                            st.toast(
                                t(
                                    "Failed to fetch models, please check API Key and Base URL"
                                ),
                                icon="❌",
                            )

                model_list = st.session_state.get("_model_list", None)

                sb_key = "model_searchbox"
                selected = st_searchbox(
                    _search_models,
                    placeholder=t("Search or enter model name"),
                    default=current_model if current_model else None,
                    default_searchterm=current_model if current_model else "",
                    default_use_searchterm=True,
                    default_options=model_list if model_list else None,
                    key=sb_key,
                    clear_on_submit=False,
                )
                if selected and selected != load_key("api.model"):
                    update_key("api.model", selected)

                if st.button("📡 " + t("Check API"), key="api", use_container_width=True):
                    with st.spinner(t("Check API") + "..."):
                        is_valid = check_api()
                    st.toast(
                        t("API Key is valid") if is_valid else t("API Key is invalid"),
                        icon="✅" if is_valid else "❌",
                    )
            except ImportError:
                c1, c2 = st.columns([4, 1])
                with c1:
                    config_input(
                        t("MODEL"),
                        model_key,
                        default=current_model,
                        help=t("click to check API validity") + " 👉",
                        placeholder=t("Search or enter model name"),
                    )
                with c2:
                    if st.button("📡", key="api"):
                        is_valid = check_api()
                        st.toast(
                            t("API Key is valid") if is_valid else t("API Key is invalid"),
                            icon="✅" if is_valid else "❌",
                        )
        current_model = configured_model(load_key_or, load_key, protocol)
        profile = reasoning_profile(current_model, protocol)
        current_effort = configured_reasoning(load_key_or, current_model, protocol)
        effort_labels = {"default": t("Auto / Default") if protocol == "cc_switch" else t("Model default"), "none": t("Thinking off"),
                         "off": t("Thinking off"), "on": t("Thinking on"),
                         "minimal": t("Minimal"), "low": t("Low"), "medium": t("Medium"),
                         "high": t("High"), "xhigh": t("Very High") if protocol == "cc_switch" else t("Extra high"),
                         "max": t("Maximum"), "maximum": t("Maximum")}
        effort = st.selectbox(
            t("Reasoning Effort"), profile["levels"],
            index=profile["levels"].index(current_effort),
            format_func=effort_labels.get, key="reasoning_" + profile["family"],
            disabled=len(profile["levels"]) == 1,
            help=t("CC Switch handles reasoning conversion. Auto uses provider defaults; Gemini Native currently omits explicit effort.")
            if protocol == "cc_switch" else t("Options follow the current model's actual capabilities. Settings are saved separately for each model family."),
        )
        if effort != current_effort:
            effort_key = "api.cc_switch_reasoning" if protocol == "cc_switch" else "api.reasoning_effort_" + profile["family"]
            update_key(effort_key, effort, create=True)
        if profile["note"]:
            st.caption(t(profile["note"]))
        if protocol == "cc_switch" or (protocol == "anthropic" and profile["family"] == "claude"):
            current_cache = load_key_or("api.prompt_cache", True)
            cache = st.toggle(t("Claude Prompt Cache"), value=current_cache,
                              help=t("Caches stable instructions when the model's minimum prefix length is met; output tokens are still billed."))
            if cache != current_cache:
                update_key("api.prompt_cache", cache, create=True)

        llm_support_json = st.toggle(
            t("LLM JSON Format Support"),
            value=load_key("api.llm_support_json"),
            help=t("Enable if your LLM supports JSON mode output"),
            disabled=protocol != "openai",
        )
        if llm_support_json != load_key("api.llm_support_json"):
            update_key("api.llm_support_json", llm_support_json)
            st.rerun()
    with st.expander(t("Subtitles Settings"), expanded=True):
        c1, c2 = st.columns(2)
        with c1:
            langs = {
                "Auto": "auto",
                "🇺🇸 English": "en",
                "🇨🇳 简体中文": "zh",
                "🇪🇸 Español": "es",
                "🇷🇺 Русский": "ru",
                "🇫🇷 Français": "fr",
                "🇩🇪 Deutsch": "de",
                "🇮🇹 Italiano": "it",
                "🇯🇵 日本語": "ja",
            }
            lang = st.selectbox(
                t("Recog Lang"),
                options=list(langs.keys()),
                index=list(langs.values()).index(load_key("whisper.language")),
            )
            if langs[lang] != load_key("whisper.language"):
                update_key("whisper.language", langs[lang])
                st.rerun()

        runtimes = ["local", "elevenlabs"]
        configured_runtime = load_key("whisper.runtime")
        if configured_runtime not in runtimes:
            st.warning(t("The 302.ai WhisperX cloud service has been retired. Select Local or ElevenLabs to continue."))
        runtime = st.selectbox(
            t("WhisperX Runtime"),
            options=runtimes,
            index=runtimes.index(configured_runtime) if configured_runtime in runtimes else None,
            format_func=lambda x: {
                "local": t("Local"),
                "elevenlabs": t("ElevenLabs"),
            }[x],
            help=t(
                "Local runtime requires >8GB GPU; ElevenLabs runtime requires an ElevenLabs API key."
            ),
        )
        if runtime is not None and runtime != configured_runtime:
            update_key("whisper.runtime", runtime)
            st.rerun()
        if runtime == "elevenlabs":
            config_input(t("ElevenLabs API"), "whisper.elevenlabs_api_key")

        with c2:
            target_language = st.text_input(
                t("Target Lang"),
                value=load_key("target_language"),
                help=t(
                    "Input any language in natural language, as long as llm can understand"
                ),
            )
            if target_language != load_key("target_language"):
                update_key("target_language", target_language)
                st.rerun()

        demucs = st.toggle(
            t("Vocal separation enhance"),
            value=load_key("demucs"),
            help=t(
                "Recommended for videos with loud background noise, but will increase processing time"
            ),
        )
        if demucs != load_key("demucs"):
            update_key("demucs", demucs)
            st.rerun()

        from core._1_ytdlp import is_audio_only_input
        audio_only = is_audio_only_input()
        if audio_only:
            st.toggle(
                t("Burn-in Subtitles"),
                value=False,
                disabled=True,
                help=t("Audio-only input produces subtitle files only; no video is generated."),
            )
        else:
            burn_subtitles = st.toggle(
                t("Burn-in Subtitles"),
                value=load_key("burn_subtitles"),
                help=t(
                    "Whether to burn subtitles into the video, will increase processing time"
                ),
            )
            if burn_subtitles != load_key("burn_subtitles"):
                update_key("burn_subtitles", burn_subtitles)
                st.rerun()
    with st.expander(t("Dubbing Settings"), expanded=True):
        tts_methods = [
            "azure_tts",
            "openai_tts",
            "fish_tts",
            "sf_fish_tts",
            "edge_tts",
            "gpt_sovits",
            "custom_tts",
            "sf_cosyvoice2",
            "f5tts",
        ]
        tts_method_labels = {
            "azure_tts": t("Azure TTS"),
            "openai_tts": t("OpenAI TTS"),
            "fish_tts": t("Fish TTS"),
            "sf_fish_tts": t("SiliconFlow Fish TTS"),
            "edge_tts": t("Edge TTS"),
            "gpt_sovits": t("GPT-SoVITS"),
            "custom_tts": t("Custom TTS"),
            "sf_cosyvoice2": t("SiliconFlow CosyVoice2"),
            "f5tts": t("F5-TTS"),
        }
        select_tts = st.selectbox(
            t("TTS Method"),
            options=tts_methods,
            index=tts_methods.index(load_key("tts_method")),
            format_func=lambda x: tts_method_labels[x],
        )
        if select_tts != load_key("tts_method"):
            update_key("tts_method", select_tts)
            st.rerun()

        # sub settings for each tts method
        if select_tts == "sf_fish_tts":
            config_input(t("SiliconFlow API Key"), "sf_fish_tts.api_key")

            # Add mode selection dropdown
            mode_options = {
                "preset": t("Preset"),
                "custom": t("Refer_stable"),
                "dynamic": t("Refer_dynamic"),
            }
            selected_mode = st.selectbox(
                t("Mode Selection"),
                options=list(mode_options.keys()),
                format_func=lambda x: mode_options[x],
                index=list(mode_options.keys()).index(load_key("sf_fish_tts.mode"))
                if load_key("sf_fish_tts.mode") in mode_options.keys()
                else 0,
            )
            if selected_mode != load_key("sf_fish_tts.mode"):
                update_key("sf_fish_tts.mode", selected_mode)
                st.rerun()
            if selected_mode == "preset":
                config_input(t("Voice"), "sf_fish_tts.voice")

        elif select_tts == "openai_tts":
            config_input(t("302ai API"), "openai_tts.api_key")
            config_input(t("OpenAI Voice"), "openai_tts.voice")

        elif select_tts == "fish_tts":
            config_input(t("302ai API"), "fish_tts.api_key")
            fish_tts_character = st.selectbox(
                t("Fish TTS Character"),
                options=list(load_key("fish_tts.character_id_dict").keys()),
                index=list(load_key("fish_tts.character_id_dict").keys()).index(
                    load_key("fish_tts.character")
                ),
            )
            if fish_tts_character != load_key("fish_tts.character"):
                update_key("fish_tts.character", fish_tts_character)
                st.rerun()

        elif select_tts == "azure_tts":
            config_input(t("302ai API"), "azure_tts.api_key")
            config_input(t("Azure Voice"), "azure_tts.voice")

        elif select_tts == "gpt_sovits":
            st.info(t("Please refer to Github homepage for GPT_SoVITS configuration"))
            config_input(t("SoVITS Character"), "gpt_sovits.character")

            refer_mode_options = {
                1: t("Mode 1: Use provided reference audio only"),
                2: t("Mode 2: Use first audio from video as reference"),
                3: t("Mode 3: Use each audio from video as reference"),
            }
            selected_refer_mode = st.selectbox(
                t("Refer Mode"),
                options=list(refer_mode_options.keys()),
                format_func=lambda x: refer_mode_options[x],
                index=list(refer_mode_options.keys()).index(
                    load_key("gpt_sovits.refer_mode")
                ),
                help=t("Configure reference audio mode for GPT-SoVITS"),
            )
            if selected_refer_mode != load_key("gpt_sovits.refer_mode"):
                update_key("gpt_sovits.refer_mode", selected_refer_mode)
                st.rerun()

        elif select_tts == "edge_tts":
            config_input(t("Edge TTS Voice"), "edge_tts.voice")

        elif select_tts == "sf_cosyvoice2":
            config_input(t("SiliconFlow API Key"), "sf_cosyvoice2.api_key")

        elif select_tts == "f5tts":
            config_input(t("302ai API"), "f5tts.302_api")


def check_api():
    try:
        resp = ask_gpt(
            "This is a test, response 'message':'success' in json format.",
            resp_type="json",
            log_title="None",
            use_cache=False,
        )
        return resp.get("message") == "success"
    except Exception:
        return False


if __name__ == "__main__":
    check_api()
