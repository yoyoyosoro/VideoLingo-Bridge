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
    output_dir: str | Path, selected_files: Sequence[str]
) -> bytes:
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

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in selected:
            archive.write(output_path / name, arcname=name)
    return buffer.getvalue()
