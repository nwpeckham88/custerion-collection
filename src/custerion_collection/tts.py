from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from threading import Lock

from custerion_collection.config import data_dir
from custerion_collection.storage import latest_json_artifact_for_slug, latest_markdown_artifact_for_slug

_TTS_LOCK = Lock()
_TTS_ENGINE = None
_TTS_MODEL = ""


def _tts_model_name() -> str:
    return os.getenv("TTS_MODEL_NAME", "tts_models/en/vctk/vits").strip()


def _tts_cache_dir() -> Path:
    raw = os.getenv("TTS_CACHE_DIR", "").strip()
    if raw:
        target = Path(raw).expanduser().resolve()
    else:
        target = (data_dir() / "tts-cache").resolve()
    target.mkdir(parents=True, exist_ok=True)
    return target


def _tts_audio_dir() -> Path:
    target = (data_dir() / "artifacts" / "tts").resolve()
    target.mkdir(parents=True, exist_ok=True)
    return target


def _load_tts_engine():
    global _TTS_ENGINE, _TTS_MODEL

    model = _tts_model_name()
    with _TTS_LOCK:
        if _TTS_ENGINE is not None and _TTS_MODEL == model:
            return _TTS_ENGINE

        os.environ.setdefault("TTS_HOME", str(_tts_cache_dir()))

        try:
            from TTS.api import TTS  # type: ignore
        except Exception as exc:  # pragma: no cover - runtime dependency guard
            raise RuntimeError(
                "Local TTS runtime is unavailable. Install Coqui TTS with 'pip install TTS'."
            ) from exc

        _TTS_ENGINE = TTS(model_name=model, progress_bar=False, gpu=False)
        _TTS_MODEL = model
        return _TTS_ENGINE


def _sanitize_voice(voice: str) -> str:
    return re.sub(r"[^a-z0-9_-]+", "-", voice.lower()).strip("-") or "default"


def _markdown_to_tts_text(markdown: str, title: str) -> str:
    text = markdown
    text = re.sub(r"```[\s\S]*?```", " ", text)
    text = re.sub(r"\[(.*?)\]\((.*?)\)", r"\1", text)
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"^#{1,6}\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"\n{2,}", "\n", text)
    text = text.strip()
    return f"{title}. {text}" if text else title


def _first_sentence(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip()
    if not cleaned:
        return ""
    match = re.search(r"[.!?]", cleaned)
    if match:
        end = match.end()
        return cleaned[:end]
    return cleaned[:220].rstrip() + ("..." if len(cleaned) > 220 else "")


def _artifact_summary_to_tts_text(slug: str) -> str | None:
    json_path = latest_json_artifact_for_slug(slug)
    if json_path is None or not json_path.exists():
        return None

    try:
        payload = json.loads(json_path.read_text(encoding="utf-8"))
    except Exception:
        return None

    if not isinstance(payload, dict):
        return None

    film = payload.get("film")
    title = "Film report"
    if isinstance(film, dict):
        film_title = film.get("title")
        film_year = film.get("year")
        if isinstance(film_title, str) and film_title.strip():
            title = film_title.strip()
            if isinstance(film_year, int):
                title = f"{title} ({film_year})"

    lines: list[str] = [f"Summary for {title}."]

    intro = payload.get("personalized_intro")
    if isinstance(intro, str) and intro.strip():
        lines.append(_first_sentence(intro))

    sections = payload.get("sections")
    if isinstance(sections, list):
        for raw in sections[:4]:
            if not isinstance(raw, dict):
                continue
            name = str(raw.get("name") or "Section").strip()
            content = str(raw.get("content") or "").strip()
            if not content:
                continue
            sentence = _first_sentence(content)
            if sentence:
                lines.append(f"{name}: {sentence}")

    watch_next = payload.get("watch_next")
    if isinstance(watch_next, list) and watch_next:
        first = str(watch_next[0]).strip()
        if first:
            lines.append(f"Recommended next watch: {first}.")

    text = " ".join(part for part in lines if part.strip())
    cleaned = re.sub(r"\s+", " ", text).strip()
    return cleaned or None


def _voice_choices(engine) -> list[str]:
    speakers = getattr(engine, "speakers", None)
    if isinstance(speakers, list) and speakers:
        return [str(item) for item in speakers if str(item).strip()]
    return ["default"]


def list_tts_voices_for_slug(slug: str) -> tuple[str, list[str]]:
    _ = slug
    engine = _load_tts_engine()
    voices = _voice_choices(engine)
    default_voice = os.getenv("TTS_DEFAULT_VOICE", "").strip()
    if default_voice and default_voice in voices:
        return default_voice, voices
    return voices[0], voices


def synthesize_tts_audio_for_slug(
    slug: str,
    voice: str | None = None,
    mode: str = "full",
) -> Path:
    markdown_path = latest_markdown_artifact_for_slug(slug)
    if markdown_path is None or not markdown_path.exists():
        raise ValueError(f"Markdown artifact not found for slug: {slug}")

    title = slug.replace("-", " ").strip() or "Film report"
    markdown = markdown_path.read_text(encoding="utf-8")
    normalized_mode = mode.strip().lower()
    if normalized_mode not in {"summary", "full"}:
        raise ValueError("Invalid TTS mode. Use 'summary' or 'full'.")

    if normalized_mode == "summary":
        text = _artifact_summary_to_tts_text(slug) or _markdown_to_tts_text(markdown=markdown, title=title)
    else:
        text = _markdown_to_tts_text(markdown=markdown, title=title)

    engine = _load_tts_engine()
    voices = _voice_choices(engine)
    selected_voice = voice or voices[0]
    if selected_voice not in voices:
        raise ValueError(f"Unknown TTS voice: {selected_voice}")

    key = f"{_tts_model_name()}::{normalized_mode}::{selected_voice}::{text}".encode("utf-8")
    digest = hashlib.sha256(key).hexdigest()[:16]
    target = _tts_audio_dir() / f"{slug}-{_sanitize_voice(selected_voice)}-{digest}.wav"
    if target.exists():
        return target

    kwargs: dict[str, object] = {
        "text": text,
        "file_path": str(target),
    }
    if selected_voice != "default":
        kwargs["speaker"] = selected_voice

    engine.tts_to_file(**kwargs)
    return target
