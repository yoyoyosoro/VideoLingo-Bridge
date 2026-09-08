import hashlib
import os
import re
import shutil
from pathlib import Path

import streamlit as st
from core._1_ytdlp import download_video_ytdlp, find_media_file, write_input_manifest
from core.subtitle_input import (
    SOURCE_SRT_PATH,
    clear_generated_subtitle_outputs,
    clear_task_input_state,
    has_official_source,
    save_source_srt,
)
from core.utils import *
from translations.translations import translate as t

OUTPUT_DIR = "output"


def _text_task_is_active():
    runner = st.session_state.get("_text_runner")
    return bool(runner and runner.is_active)


def _clear_source_selection_metadata():
    for key in (
        "_source_srt_upload_id",
        "_source_srt_name",
        "_source_srt_error",
        "_source_subtitle_mode",
    ):
        st.session_state.pop(key, None)


def _render_source_subtitle_upload():
    st.markdown(f"**{t('Original subtitles (optional)')}**")
    uploaded_file = st.file_uploader(
        t("Upload official SRT"),
        type=["srt"],
        key="_source_srt_uploader",
        disabled=_text_task_is_active(),
        label_visibility="collapsed",
    )

    stored_upload_id = st.session_state.get("_source_srt_upload_id")
    if uploaded_file is not None:
        payload = uploaded_file.getvalue()
        upload_id = f"{uploaded_file.name}:{hashlib.sha256(payload).hexdigest()}"
        if upload_id != stored_upload_id or not has_official_source():
            try:
                save_source_srt(payload)
            except ValueError as exc:
                clear_generated_subtitle_outputs()
                Path(SOURCE_SRT_PATH).unlink(missing_ok=True)
                _clear_source_selection_metadata()
                st.session_state["_source_srt_error"] = str(exc)
                st.error(t("Invalid SRT: {error}").replace("{error}", str(exc)))
                return False

            clear_generated_subtitle_outputs()
            st.session_state["_source_srt_upload_id"] = upload_id
            st.session_state["_source_srt_name"] = uploaded_file.name
            st.session_state["_source_subtitle_mode"] = "official"
            st.session_state.pop("_source_srt_error", None)

        selected_name = st.session_state.get("_source_srt_name", uploaded_file.name)
        st.success(t("Selected subtitle: {name}").replace("{name}", selected_name))
        st.caption(
            t("Subtitle uploaded: use official timestamps and skip Whisper / ASR.")
        )
        return True

    if stored_upload_id and not _text_task_is_active():
        clear_generated_subtitle_outputs()
        Path(SOURCE_SRT_PATH).unlink(missing_ok=True)
        _clear_source_selection_metadata()

    if has_official_source():
        selected_name = st.session_state.get("_source_srt_name", Path(SOURCE_SRT_PATH).name)
        st.success(t("Selected subtitle: {name}").replace("{name}", selected_name))
        st.caption(
            t("Subtitle uploaded: use official timestamps and skip Whisper / ASR.")
        )
        return True

    st.session_state.pop("_source_srt_error", None)
    st.caption(t("No subtitle uploaded: use the existing Whisper / ASR flow."))
    return False


def _delete_media_and_task_state():
    if os.path.exists(OUTPUT_DIR):
        shutil.rmtree(OUTPUT_DIR)
    clear_task_input_state(st.session_state)
    st.session_state.pop("_processed_upload_id", None)


def _css_text(value):
    return str(value).replace("\\", "\\\\").replace('"', '\\"')


def _inject_file_uploader_i18n():
    # Streamlit does not expose official i18n for file_uploader internals.
    # Streamlit 1.49 DOM:
    #   div[data-testid="stFileUploaderDropzoneInstructions"]
    #     > span    (cloud icon, must keep)
    #     > div     (column flex)
    #         > span  (1st: "Drag and drop ... here")
    #         > span  (2nd: "Limit ... · MP4, MOV ...")
    # So we target ONLY the two direct child spans of the inner div, leaving
    # the icon and other elements untouched.
    drag_text = _css_text(t("Drag and drop file here"))
    limit_text = _css_text(t("Limit 4GB per file · MP4, MOV, AVI, MKV, FLV, WMV, WEBM, WAV, MP3, FLAC, M4A"))
    browse_text = _css_text(t("Browse files"))
    st.markdown(
        f"""
        <style>
        /* Title line */
        div[data-testid="stFileUploaderDropzoneInstructions"] > div > span:nth-of-type(1) {{
            font-size: 0 !important;
            line-height: 1.4;
        }}
        div[data-testid="stFileUploaderDropzoneInstructions"] > div > span:nth-of-type(1)::before {{
            content: "{drag_text}";
            font-size: 1rem;
        }}
        /* Sub line (limit + accepted formats) */
        div[data-testid="stFileUploaderDropzoneInstructions"] > div > span:nth-of-type(2) {{
            font-size: 0 !important;
            line-height: 1.4;
        }}
        div[data-testid="stFileUploaderDropzoneInstructions"] > div > span:nth-of-type(2)::before {{
            content: "{limit_text}";
            font-size: 0.8rem;
        }}
        /* Browse files button */
        div[data-testid="stFileUploader"] button[kind="secondary"] {{
            font-size: 0 !important;
        }}
        div[data-testid="stFileUploader"] button[kind="secondary"]::before {{
            content: "{browse_text}";
            font-size: 0.875rem;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )

def download_video_section():
    st.header(t("a. Download or Upload Video"))
    with st.container(border=True):
        try:
            media_file, media_type = find_media_file()
            if media_type == "video":
                st.video(media_file)
            else:
                st.audio(media_file)
            _render_source_subtitle_upload()
            st.button(
                t("Delete and Reselect"),
                key="delete_video_button",
                on_click=_delete_media_and_task_state,
            )
            return True
        except ValueError as e:
            if "No media file found" not in str(e):
                st.error(t("Media file detection failed: {error}").replace("{error}", str(e)))
                st.button(
                    t("Clear output and reselect"),
                    key="clear_output_button",
                    on_click=_delete_media_and_task_state,
                )
                return False
        except Exception:
            pass

        col1, col2 = st.columns([3, 1])
        with col1:
            url = st.text_input(t("Enter YouTube link:"))
        with col2:
            res_dict = {
                "360p": "360",
                "1080p": "1080",
                t("Best"): "best"
            }
            target_res = load_key("ytb_resolution")
            res_options = list(res_dict.keys())
            default_idx = list(res_dict.values()).index(target_res) if target_res in res_dict.values() else 0
            res_display = st.selectbox(t("Resolution"), options=res_options, index=default_idx)
            res = res_dict[res_display]
        if st.button(t("Download Video"), key="download_button", width="stretch"):
            if url:
                if os.path.exists(OUTPUT_DIR):
                    shutil.rmtree(OUTPUT_DIR)
                clear_task_input_state(st.session_state)
                st.session_state.pop("_processed_upload_id", None)
                with st.spinner(t("Downloading video...")):
                    download_video_ytdlp(url, resolution=res)
                st.rerun()

        _inject_file_uploader_i18n()
        uploaded_file = st.file_uploader(t("Upload local media file"), type=load_key("allowed_video_formats") + load_key("allowed_audio_formats"))
        if uploaded_file:
            upload_id = f"{uploaded_file.name}:{uploaded_file.size}"
            if st.session_state.get("_processed_upload_id") == upload_id:
                try:
                    find_media_file()
                    st.warning(t("Upload was already processed. Delete and reselect to upload again."))
                    return False
                except Exception:
                    st.session_state.pop("_processed_upload_id", None)

            if os.path.exists(OUTPUT_DIR):
                shutil.rmtree(OUTPUT_DIR)
            clear_task_input_state(st.session_state)
            os.makedirs(OUTPUT_DIR, exist_ok=True)

            raw_name = uploaded_file.name.replace(' ', '_')
            name, ext = os.path.splitext(raw_name)
            clean_name = re.sub(r'[^\w\-_\.]', '', name) + ext.lower()
                
            with open(os.path.join(OUTPUT_DIR, clean_name), "wb") as f:
                f.write(uploaded_file.getbuffer())

            media_path = os.path.join(OUTPUT_DIR, clean_name)
            media_ext = ext.lower().lstrip(".")
            media_type = "video" if media_ext in load_key("allowed_video_formats") else "audio"
            write_input_manifest(media_path, media_type, original_name=uploaded_file.name)

            st.session_state["_processed_upload_id"] = upload_id
            st.rerun()
        else:
            return False
