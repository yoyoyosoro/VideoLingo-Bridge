from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping, MutableMapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path


SOURCE_SRT_PATH = Path("output/log/source_input.srt")
SOURCE_SUBTITLE_DATA_PATH = Path("output/log/source_subtitles.json")
SUBTITLE_OUTPUT_FILENAMES = (
    "src.srt",
    "trans.srt",
    "src_trans.srt",
    "trans_src.srt",
)
TASK_INPUT_STATE_KEYS = (
    "_source_srt_uploader",
    "_source_srt_upload_id",
    "_source_srt_name",
    "_source_srt_error",
    "_source_subtitle_mode",
    "_video_style_input",
    "_video_style_snapshot",
    "_subtitle_zip_selection",
)
GENERATED_SUBTITLE_RELATIVE_PATHS = (
    ".subtitle_done",
    "src.srt",
    "trans.srt",
    "src_trans.srt",
    "trans_src.srt",
    "output_sub.mp4",
    "log/cleaned_chunks.xlsx",
    "log/split_by_nlp.txt",
    "log/split_by_meaning.txt",
    "log/terminology.json",
    "log/translation_results.xlsx",
    "log/translation_results_for_subtitles.xlsx",
    "log/translation_results_remerged.xlsx",
    "log/source_subtitles.json",
)

_TIMING_RE = re.compile(
    r"^(?P<start>\d{2,}:\d{2}:\d{2}[,.]\d{3})"
    r"\s*-->\s*"
    r"(?P<end>\d{2,}:\d{2}:\d{2}[,.]\d{3})"
    r"(?:\s+.*)?$"
)


@dataclass(frozen=True)
class SubtitleCue:
    stable_id: str
    index: str
    start: str
    end: str
    timing_line: str
    text: str


def _timestamp_to_milliseconds(value: str) -> int:
    hours, minutes, seconds_part = value.replace(".", ",").split(":")
    seconds, milliseconds = seconds_part.split(",")
    if int(minutes) > 59 or int(seconds) > 59:
        raise ValueError(f"invalid timestamp: {value}")
    return (
        int(hours) * 3_600_000
        + int(minutes) * 60_000
        + int(seconds) * 1_000
        + int(milliseconds)
    )


def parse_srt(content: str | bytes) -> list[SubtitleCue]:
    """Parse valid SRT cues while preserving authoritative cue fields.

    Newline encoding and block separators are normalized for parsing. Cue index,
    timestamp strings, ordering, intra-cue line structure, spacing, and text are
    otherwise retained. Empty cues are ignored; malformed non-empty cues fail
    closed so later cues cannot be shifted onto the wrong timestamp.
    """

    if isinstance(content, bytes):
        try:
            content = content.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise ValueError("SRT must be UTF-8 encoded") from exc
    else:
        content = content.removeprefix("\ufeff")

    normalized = content.replace("\r\n", "\n").replace("\r", "\n")
    blocks = re.split(r"\n[ \t]*\n", normalized)
    cues: list[SubtitleCue] = []

    for block_number, raw_block in enumerate(blocks, start=1):
        block = raw_block.strip("\n")
        if not block.strip():
            continue

        lines = block.split("\n")
        if len(lines) < 2 or not lines[0].strip():
            raise ValueError(f"Malformed SRT cue {block_number}: missing index or timing")

        timing_match = _TIMING_RE.fullmatch(lines[1].strip())
        if timing_match is None:
            raise ValueError(f"Malformed SRT cue {lines[0].strip() or block_number}: invalid timing")

        start = timing_match.group("start")
        end = timing_match.group("end")
        try:
            if _timestamp_to_milliseconds(end) < _timestamp_to_milliseconds(start):
                raise ValueError("end precedes start")
        except ValueError as exc:
            raise ValueError(
                f"Malformed SRT cue {lines[0].strip() or block_number}: {exc}"
            ) from exc

        text = "\n".join(lines[2:])
        if not text.strip():
            continue

        cues.append(
            SubtitleCue(
                stable_id=f"cue-{len(cues) + 1:06d}",
                index=lines[0],
                start=start,
                end=end,
                timing_line=lines[1],
                text=text,
            )
        )

    if not cues:
        raise ValueError("SRT contains no valid non-empty cues")
    return cues


def save_source_srt(
    content: str | bytes, path: str | Path = SOURCE_SRT_PATH
) -> list[SubtitleCue]:
    cues = parse_srt(content)
    payload = content if isinstance(content, bytes) else content.encode("utf-8")
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(payload)
    return cues


def load_source_srt(path: str | Path = SOURCE_SRT_PATH) -> list[SubtitleCue]:
    return parse_srt(Path(path).read_bytes())


def has_official_source(path: str | Path = SOURCE_SRT_PATH) -> bool:
    return Path(path).is_file()


def clear_generated_subtitle_outputs(output_dir: str | Path = "output") -> None:
    output_path = Path(output_dir)
    for relative_path in GENERATED_SUBTITLE_RELATIVE_PATHS:
        path = output_path / relative_path
        if path.is_file():
            path.unlink()


def source_text_for_translation(cue: SubtitleCue) -> str:
    """Return a one-request-line copy without mutating the source cue."""

    return re.sub(r"[\r\n]+", " ", cue.text).strip()


def combined_source_text(cues: Sequence[SubtitleCue]) -> str:
    return "\n".join(source_text_for_translation(cue) for cue in cues)


def _validate_translation_mapping(
    cues: Sequence[SubtitleCue], translations: Mapping[str, str]
) -> None:
    expected = [cue.stable_id for cue in cues]
    actual = list(translations)
    missing = [cue_id for cue_id in expected if cue_id not in translations]
    unexpected = [cue_id for cue_id in actual if cue_id not in expected]
    empty = [
        cue_id
        for cue_id in expected
        if cue_id in translations and not str(translations[cue_id]).strip()
    ]
    if missing or unexpected or empty:
        details = []
        if missing:
            details.append(f"missing IDs: {', '.join(missing)}")
        if unexpected:
            details.append(f"unexpected IDs: {', '.join(unexpected)}")
        if empty:
            details.append(f"empty translations: {', '.join(empty)}")
        raise ValueError("Invalid official subtitle translation mapping: " + "; ".join(details))


def _render_cues(cues: Sequence[SubtitleCue], text_by_id: Mapping[str, str]) -> str:
    blocks = [
        f"{cue.index}\n{cue.timing_line}\n{text_by_id[cue.stable_id]}"
        for cue in cues
    ]
    return "\n\n".join(blocks) + "\n"


def render_subtitle_variants(
    cues: Sequence[SubtitleCue], translations: Mapping[str, str]
) -> dict[str, str]:
    _validate_translation_mapping(cues, translations)

    source = {cue.stable_id: cue.text for cue in cues}
    translated = {
        cue.stable_id: str(translations[cue.stable_id]).strip() for cue in cues
    }
    source_then_translation = {
        cue.stable_id: f"{cue.text}\n{translated[cue.stable_id]}" for cue in cues
    }
    translation_then_source = {
        cue.stable_id: f"{translated[cue.stable_id]}\n{cue.text}" for cue in cues
    }

    return {
        "src.srt": _render_cues(cues, source),
        "trans.srt": _render_cues(cues, translated),
        "src_trans.srt": _render_cues(cues, source_then_translation),
        "trans_src.srt": _render_cues(cues, translation_then_source),
    }


def write_subtitle_variants(
    cues: Sequence[SubtitleCue],
    translations: Mapping[str, str],
    output_dir: str | Path = "output",
) -> list[str]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    rendered = render_subtitle_variants(cues, translations)
    written: list[str] = []
    for filename in SUBTITLE_OUTPUT_FILENAMES:
        path = output_path / filename
        path.write_text(rendered[filename], encoding="utf-8", newline="\n")
        written.append(str(path))
    return written


def _batch_cues(
    cues: Sequence[SubtitleCue], max_batch_items: int, max_batch_chars: int
) -> list[list[SubtitleCue]]:
    if max_batch_items < 1 or max_batch_chars < 1:
        raise ValueError("Batch limits must be positive")

    batches: list[list[SubtitleCue]] = []
    current: list[SubtitleCue] = []
    current_chars = 0
    for cue in cues:
        text_length = len(source_text_for_translation(cue))
        if current and (
            len(current) >= max_batch_items
            or current_chars + text_length > max_batch_chars
        ):
            batches.append(current)
            current = []
            current_chars = 0
        current.append(cue)
        current_chars += text_length
    if current:
        batches.append(current)
    return batches


def translate_official_cues(
    cues: Sequence[SubtitleCue],
    translate_batch: Callable[[list[dict[str, str]], list[str] | None, list[str] | None, int], Mapping[str, str]],
    *,
    max_batch_items: int = 10,
    max_batch_chars: int = 600,
) -> dict[str, str]:
    """Translate official cues in batches and restore by stable ID."""

    batches = _batch_cues(cues, max_batch_items, max_batch_chars)
    translations: dict[str, str] = {}

    for batch_index, batch in enumerate(batches):
        items = [
            {"id": cue.stable_id, "text": source_text_for_translation(cue)}
            for cue in batch
        ]
        previous_content = (
            [source_text_for_translation(cue) for cue in batches[batch_index - 1][-3:]]
            if batch_index > 0
            else None
        )
        after_content = (
            [source_text_for_translation(cue) for cue in batches[batch_index + 1][:2]]
            if batch_index + 1 < len(batches)
            else None
        )
        result = translate_batch(items, previous_content, after_content, batch_index)
        if not isinstance(result, Mapping):
            raise ValueError(f"Translation batch {batch_index} did not return an ID mapping")
        _validate_translation_mapping(batch, result)
        for cue in batch:
            translations[cue.stable_id] = str(result[cue.stable_id]).strip()

    _validate_translation_mapping(cues, translations)
    return translations


def _create_videolingo_batch_translator(video_style: str):
    from core._4_1_summarize import search_things_to_note_in_prompt
    from core.translate_lines import translate_lines
    from core.utils import check_cancel
    from core.utils.models import _4_1_TERMINOLOGY

    with open(_4_1_TERMINOLOGY, "r", encoding="utf-8") as file:
        theme_prompt = json.load(file).get("theme")

    def translate_batch(items, previous_content, after_content, batch_index):
        check_cancel()
        lines = "\n".join(item["text"] for item in items)
        item_ids = [item["id"] for item in items]
        things_to_note = search_things_to_note_in_prompt(lines)
        translated, _ = translate_lines(
            lines,
            previous_content,
            after_content,
            things_to_note,
            theme_prompt,
            batch_index,
            item_ids=item_ids,
            video_style=video_style,
        )
        translated_lines = translated.split("\n")
        if len(translated_lines) != len(item_ids):
            raise ValueError(
                f"Official subtitle batch {batch_index} returned the wrong cue count"
            )
        return dict(zip(item_ids, translated_lines))

    return translate_batch


def translate_and_write_official_subtitles(
    cues: Sequence[SubtitleCue],
    *,
    video_style: str = "",
    output_dir: str | Path = "output",
    translate_batch=None,
) -> list[str]:
    batch_translator = translate_batch or _create_videolingo_batch_translator(
        video_style
    )
    translations = translate_official_cues(cues, batch_translator)
    return write_subtitle_variants(cues, translations, output_dir)


def save_structured_cues(
    cues: Sequence[SubtitleCue], path: str | Path = SOURCE_SUBTITLE_DATA_PATH
) -> str:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps([asdict(cue) for cue in cues], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return str(target)


def clear_task_input_state(session_state: MutableMapping) -> None:
    for key in TASK_INPUT_STATE_KEYS:
        session_state.pop(key, None)
