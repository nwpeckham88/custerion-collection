from __future__ import annotations

import hashlib
import json
import os
import re
import urllib.request
import wave
from array import array
from pathlib import Path
from threading import Lock

from custerion_collection.config import data_dir
from custerion_collection.storage import latest_json_artifact_for_slug, latest_markdown_artifact_for_slug

_TTS_LOCK = Lock()
_TTS_ENGINE = None


def _tts_enabled() -> bool:
    raw = os.getenv("ENABLE_TTS", "0").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _ensure_tts_enabled() -> None:
    if not _tts_enabled():
        raise RuntimeError("TTS is disabled. Set ENABLE_TTS=1 and install optional dependencies to enable it.")


def tts_runtime_label() -> str:
    return "kokoro-onnx"


def _tts_cache_dir() -> Path:
    raw = os.getenv("TTS_CACHE_DIR", "").strip()
    if raw:
        target = Path(raw).expanduser().resolve()
    else:
        target = (data_dir() / "tts-cache").resolve()
    target.mkdir(parents=True, exist_ok=True)
    return target


def _kokoro_model_path() -> Path:
    return _tts_cache_dir() / "kokoro-v1.0.onnx"


def _kokoro_voices_path() -> Path:
    return _tts_cache_dir() / "voices-v1.0.bin"


def _download_if_missing(target: Path, url: str) -> None:
    if target.exists():
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    urllib.request.urlretrieve(url, str(target))


def _tts_audio_dir() -> Path:
    target = (data_dir() / "artifacts" / "tts").resolve()
    target.mkdir(parents=True, exist_ok=True)
    return target


def _load_tts_engine():
    global _TTS_ENGINE

    _ensure_tts_enabled()
    with _TTS_LOCK:
        if _TTS_ENGINE is not None:
            return _TTS_ENGINE

        try:
            from kokoro_onnx import Kokoro  # type: ignore
        except Exception as exc:  # pragma: no cover - runtime dependency guard
            raise RuntimeError(
                "Kokoro TTS runtime is unavailable. Install optional dependencies with 'pip install -e .[tts]'."
            ) from exc

        model_url = os.getenv(
            "KOKORO_MODEL_URL",
            "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx",
        ).strip()
        voices_url = os.getenv(
            "KOKORO_VOICES_URL",
            "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin",
        ).strip()

        model_path = _kokoro_model_path()
        voices_path = _kokoro_voices_path()
        _download_if_missing(model_path, model_url)
        _download_if_missing(voices_path, voices_url)

        _TTS_ENGINE = Kokoro(str(model_path), str(voices_path))
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


def _voice_choices() -> list[str]:
    raw = os.getenv("TTS_ENGLISH_VOICES", "").strip()
    if raw:
        voices = [item.strip() for item in raw.split(",") if item.strip()]
        if voices:
            return voices
    return [os.getenv("TTS_DEFAULT_VOICE", "af_sarah").strip() or "af_sarah"]


def _lang_code() -> str:
    return "en-us"


def _write_wav(path: Path, samples, sample_rate: int) -> None:
    values = samples.tolist() if hasattr(samples, "tolist") else list(samples)
    frames = array("h")
    for sample in values:
        scalar = float(sample)
        if scalar > 1.0:
            scalar = 1.0
        if scalar < -1.0:
            scalar = -1.0
        frames.append(int(scalar * 32767.0))

    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(int(sample_rate))
        wav_file.writeframes(frames.tobytes())


def list_tts_voices_for_slug(slug: str) -> tuple[str, list[str]]:
    _ = slug
    _ensure_tts_enabled()
    _ = _load_tts_engine()
    voices = _voice_choices()

    default_voice = os.getenv("TTS_DEFAULT_VOICE", "").strip()
    if default_voice and default_voice in voices:
        return default_voice, voices
    return voices[0], voices


def synthesize_tts_audio_for_slug(
    slug: str,
    voice: str | None = None,
    mode: str = "full",
) -> Path:
    _ensure_tts_enabled()
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
    voices = _voice_choices()

    selected_voice = voice or voices[0]
    if selected_voice not in voices:
        raise ValueError(f"Unknown TTS voice: {selected_voice}")

    key = f"{tts_runtime_label()}::{normalized_mode}::{selected_voice}::{_lang_code()}::{text}".encode("utf-8")
    digest = hashlib.sha256(key).hexdigest()[:16]
    target = _tts_audio_dir() / f"{slug}-{_sanitize_voice(selected_voice)}-{digest}.wav"
    if target.exists():
        return target

    samples, sample_rate = engine.create(text, voice=selected_voice, speed=1.0, lang=_lang_code())
    _write_wav(target, samples=samples, sample_rate=int(sample_rate))

    return target
