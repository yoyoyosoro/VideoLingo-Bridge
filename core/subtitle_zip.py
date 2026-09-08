from __future__ import annotations

import io
import zipfile
from collections.abc import Sequence
from pathlib import Path


ALLOWED_SUBTITLE_FILES = (
    "src.srt",
    "trans.srt",
    "src_trans.srt",
    "trans_src.srt",
)


def build_subtitle_zip_bytes(
    output_dir: str | Path, selected_files: Sequence[str], media_name: str | None = None
) -> bytes:
    selected = _validate_selection(output_dir, selected_files)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in selected:
            archive.write(Path(output_dir) / name, arcname=_download_filename(name, media_name))
    return buffer.getvalue()


def _download_filename(filename, media_name):
    if not media_name:
        return filename
    stem = Path(media_name.replace("\\", "/")).stem
    prefix = "tran" if filename == "trans.srt" else Path(filename).stem
    return f"{prefix}丨{stem}{Path(filename).suffix}"


def build_subtitle_download(output_dir, selected_files, media_name=None):
    selected = _validate_selection(output_dir, selected_files)
    if len(selected) == 1:
        name = selected[0]
        return (Path(output_dir) / name).read_bytes(), _download_filename(name, media_name), "application/x-subrip"
    return (
        build_subtitle_zip_bytes(output_dir, selected, media_name),
        _download_filename("subtitles.zip", media_name),
        "application/zip",
    )


def _validate_selection(output_dir, selected_files):
    selected = list(selected_files)
    if not selected:
        raise ValueError("Select at least one subtitle file")
    if len(set(selected)) != len(selected):
        raise ValueError("Subtitle selections must not contain duplicates")

    unsupported = [name for name in selected if name not in ALLOWED_SUBTITLE_FILES]
    if unsupported:
        raise ValueError(f"Unsupported subtitle file: {unsupported[0]}")

    output_path = Path(output_dir)
    missing = [name for name in selected if not (output_path / name).is_file()]
    if missing:
        raise FileNotFoundError(f"Subtitle file not found: {missing[0]}")

    return selected
