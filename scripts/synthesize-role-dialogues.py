#!/usr/bin/env python3
"""Render Greek source readings or new monologues/dialogues with local LFM only."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import unicodedata
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
MODEL = "lfm3-audio:2b-q8_0"
LEGACY_FFMPEG = "/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg"
LEGACY_WHISPER = "/opt/homebrew/bin/whisper-cli"
DEFAULT_ASR_MODEL = Path.home() / "Library/Caches/greek-context/whisper.cpp/ggml-large-v3.bin"
np = None
sf = None
PROFILE = {"name": "natural-conversation-two-voices-v2", "tempo": 1.0,
           "pause_seconds": 0.35, "scene_pause_seconds": 1.4,
           "exterior_speech_padding_ms": 100, "edge_fade_ms": 5,
           "bounded_turn_rms_target": 0.1, "loudnorm": "I=-18:TP=-1.5:LRA=11"}


def load_audio_dependencies():
    global np, sf
    if np is None or sf is None:
        try:
            import numpy as numpy_module
            import soundfile as soundfile_module
        except ImportError as error:
            raise RuntimeError(
                "Missing Python audio dependencies. In your Python environment run: "
                f"{sys.executable} -m pip install numpy soundfile"
            ) from error
        np, sf = numpy_module, soundfile_module


def resolve_executable(value, environment, command, legacy):
    configured = value or os.environ.get(environment)
    if configured:
        expanded = os.path.expanduser(str(configured))
        path = shutil.which(expanded)
        if path:
            return path
        raise ValueError(f"Executable not found: {configured}. Set --{command} or {environment} to an executable path.")
    path = shutil.which(command)
    if path:
        return path
    if Path(legacy).is_file() and os.access(legacy, os.X_OK):
        return legacy
    raise ValueError(f"Missing {command}. Install it on PATH or set --{command} /path/to/{command} ({environment}).")


def resolve_tools(ffmpeg=None, whisper_cli=None, asr_model=None, check_asr=False):
    tools = {"ffmpeg": resolve_executable(ffmpeg, "GREEK_CONTEXT_FFMPEG", "ffmpeg", LEGACY_FFMPEG)}
    if check_asr:
        tools["whisper_cli"] = resolve_executable(
            whisper_cli, "GREEK_CONTEXT_WHISPER_CLI", "whisper-cli", LEGACY_WHISPER)
        model = Path(asr_model or os.environ.get("GREEK_CONTEXT_ASR_MODEL") or DEFAULT_ASR_MODEL).expanduser()
        if not model.is_file():
            raise ValueError("Missing Whisper ggml model. Pass --asr-model /path/to/ggml-large-v3.bin "
                             "or set GREEK_CONTEXT_ASR_MODEL to your installed model.")
        tools["asr_model"] = str(model.resolve())
    return tools


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def save(path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def request_json(url, body=None):
    request = urllib.request.Request(url, data=json.dumps(body).encode() if body is not None else None,
                                     headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=600) as response:
        return json.load(response)


def words(text):
    value = "".join(c for c in unicodedata.normalize("NFD", text.casefold())
                    if unicodedata.category(c) != "Mn")
    return re.findall(r"[^\W\d_]+", value)


def word_distance(a, b):
    previous = list(range(len(b) + 1))
    for i, word in enumerate(a, start=1):
        current = [i]
        for j, other in enumerate(b, start=1):
            current.append(min(previous[j] + 1, current[j-1] + 1,
                               previous[j-1] + (word != other)))
        previous = current
    return previous[-1]


def prepare_turn(audio, rate):
    load_audio_dependencies()
    audio = np.asarray(audio, dtype=np.float32)
    if audio.ndim == 2:
        audio = audio.mean(axis=1)
    audio = audio.reshape(-1)
    if not audio.size or not np.isfinite(audio).all() or np.max(np.abs(audio)) < 1e-5:
        raise RuntimeError("Silent or invalid generated turn")
    active = np.flatnonzero(np.abs(audio) > 0.003)
    if active.size:
        padding = int(rate * 0.1)
        audio = audio[max(0, active[0]-padding):min(len(audio), active[-1]+padding+1)].copy()
    rms = float(np.sqrt(np.mean(audio ** 2)))
    gain = min(2.0, max(0.5, 0.1 / max(rms, 1e-6)), 0.89 / float(np.max(np.abs(audio))))
    audio *= gain
    fade = min(int(rate * 0.005), len(audio)//2)
    if fade:
        audio[:fade] *= np.linspace(0, 1, fade)
        audio[-fade:] *= np.linspace(1, 0, fade)
    return audio, gain


def render(script_path, endpoint, model_digest, check_asr, tools):
    load_audio_dependencies()
    script = read(script_path)
    directory = script_path.parent
    parts = directory / "parts"
    parts.mkdir(exist_ok=True)
    generated = script.get("artifact_type") == "generated_practice"
    kind = script.get("format", "dialogue")
    if kind not in {"monologue", "dialogue"}:
        raise RuntimeError("Use monologue or dialogue format")
    stem = script.get("file_stem", kind)
    if generated and (not isinstance(stem, str) or len(stem) > 64 or not re.fullmatch(r"(?:dialogue|monologue)-[a-z0-9]+(?:-[a-z0-9]+)*", stem) or not stem.startswith(kind + "-")):
        raise RuntimeError("New practice requires a short English filename with format and topic")
    input_key = "authored_text_path" if generated else "source_transcript"
    hash_key = "authored_text_sha256" if generated else "source_sha256"
    source = ROOT / script[input_key]
    if sha(source) != script[hash_key]:
        raise RuntimeError(f"Reference transcript changed: {source}")
    voices = script["roles"]
    voice_set = {role["voice"] for role in voices.values()}
    if kind == "monologue":
        if len(voices) != 1 or not voice_set.issubset({"male-greek", "female-greek"}):
            raise RuntimeError("A monologue must have exactly one role and one Greek voice")
    elif voice_set != {"male-greek", "female-greek"}:
        raise RuntimeError("Each dialogue must use both local Greek voice presets")
    if generated and kind == "dialogue" and len(voices) != 2:
        raise RuntimeError("A new practice dialogue must have exactly two roles and two distinct voices")
    turns = script["turns"]
    if not turns or any(turn["role"] not in voices or not turn["text"].strip() for turn in turns):
        raise RuntimeError("Invalid role or empty turn")
    if {turn["role"] for turn in turns} != set(voices):
        raise RuntimeError("Every declared role must actually speak")
    text = "\n".join(turn["text"] for turn in turns) + "\n"
    # Verify that role annotation has neither added nor dropped spoken words.
    source_text = source.read_text(encoding="utf-8")
    for heading in script.get("omitted_headings", []):
        if heading not in source_text:
            raise RuntimeError(f"Heading not found: {heading}")
        source_text = source_text.replace(heading, "", 1)
    if " ".join(source_text.split()) != " ".join(text.split()):
        raise RuntimeError(f"Role script differs from the source: {script_path}")
    (directory / f"{stem}.txt").write_text(text, encoding="utf-8")
    markdown = [f"# {script['title']}", "", script["casting_note"], "", "## Роли", ""]
    for key, role in voices.items():
        markdown.append(f"- {key}: {role['label']} — `{role['voice']}`.")
    markdown.extend(["", "## Реплики", ""])
    for turn in turns:
        markdown.append(f"**{voices[turn['role']]['label']}:** {turn['text']}\n")
    (directory / f"{stem}.md").write_text("\n".join(markdown), encoding="utf-8")
    manifest = {"created_at": datetime.now(timezone.utc).isoformat(), "model": MODEL,
                "reference_type": "generated_practice" if generated else "generated_role_reading",
                "format": kind, "file_stem": stem,
                "model_digest": model_digest, "local_endpoint": endpoint,
                "profile": {**PROFILE, "name": "natural-conversation-one-voice-v2" if kind == "monologue" else PROFILE["name"]},
                "script_sha256": sha(script_path), "input_text_sha256": sha(source),
                "input_text_path": str(source.relative_to(ROOT)),
                "source_reference_id": script.get("source_reference_id"),
                "source_reference_ids": script.get("source_reference_ids", []), "roles": voices,
                "role_assignment_status": script["role_assignment_status"], "turns": []}
    sequence = []
    sample_rate = None
    position = 0
    previous_scene = None
    for number, turn in enumerate(turns, 1):
        voice = voices[turn["role"]]["voice"]
        path = parts / f"{number:03d}.wav"
        record_path = path.with_suffix(".json")
        key = hashlib.sha256(json.dumps({"text": turn["text"], "voice": voice,
                                        "model_digest": model_digest}, sort_keys=True).encode()).hexdigest()
        if path.exists() and record_path.exists() and (old := read(record_path)).get("cache_key") == key and old.get("sha256") == sha(path):
            audio, rate = sf.read(path, dtype="float32")
            record = old
        else:
            start = time.monotonic()
            request = urllib.request.Request(endpoint + "/v1/audio/speech",
                data=json.dumps({"model": MODEL, "voice": voice, "input": turn["text"],
                                 "response_format": "wav"}).encode(),
                headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(request, timeout=600) as response:
                audio, rate = sf.read(io.BytesIO(response.read()), dtype="float32")
            prepare_turn(audio, rate)  # Check before saving the raw turn.
            sf.write(path, audio, rate, subtype="PCM_16")
            record = {"cache_key": key, "sha256": sha(path), "voice": voice, "text": turn["text"],
                      "native_duration_seconds": round(len(audio) / rate, 3),
                      "generation_seconds": round(time.monotonic() - start, 3)}
            save(record_path, record)
        if sample_rate is not None and sample_rate != rate:
            raise RuntimeError("Sample rate changed between turns")
        sample_rate = rate
        if sequence:
            pause = PROFILE["scene_pause_seconds"] if turn.get("scene", 1) != previous_scene else PROFILE["pause_seconds"]
            silence = np.zeros(round(rate * pause), dtype=np.float32)
            sequence.append(silence)
            position += len(silence)
        prepared, gain = prepare_turn(audio, rate)
        sequence.append(prepared)
        manifest["turns"].append({**record, "turn": number, "role": turn["role"],
             "scene": turn.get("scene", 1), "file": str(path.relative_to(directory)),
             "assembly_gain": round(gain, 5), "pre_tempo_start_seconds": round(position / rate, 4),
             "pre_tempo_end_seconds": round((position + len(prepared)) / rate, 4)})
        position += len(prepared)
        previous_scene = turn.get("scene", 1)
        print(f"{directory.name} {number}/{len(turns)} {voice}", flush=True)
    native = directory / "native-assembled.wav"
    sf.write(native, np.concatenate(sequence), sample_rate, subtype="PCM_16")
    final = directory / f"{stem}.wav"
    subprocess.run([tools["ffmpeg"], "-nostdin", "-v", "error", "-y", "-i", str(native),
                    "-af", "loudnorm=" + PROFILE["loudnorm"], "-ar", "24000", "-ac", "1",
                    "-c:a", "pcm_s16le", str(final)], check=True)
    subprocess.run([tools["ffmpeg"], "-nostdin", "-v", "error", "-y", "-i", str(final),
                    "-c:a", "libmp3lame", "-q:a", "2", str(final.with_suffix(".mp3"))], check=True)
    audio, rate = sf.read(final, dtype="float32")
    manifest["result"] = {"mp3": final.with_suffix(".mp3").name, "wav": final.name,
                          "mp3_sha256": sha(final.with_suffix(".mp3")), "wav_sha256": sha(final),
                          "duration_seconds": round(len(audio) / rate, 3), "sample_rate": rate,
                          "peak": float(np.max(np.abs(audio))), "all_turns_present": len(turns) == len(manifest["turns"])}
    save(directory / "manifest.json", manifest)
    if check_asr:
        qa = directory / "qa"
        qa.mkdir(exist_ok=True)
        qa_audio = qa / "input-16k.wav"
        subprocess.run([tools["ffmpeg"], "-nostdin", "-v", "error", "-y", "-i", str(final),
                        "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", str(qa_audio)], check=True)
        command = [tools["whisper_cli"], "-m", tools["asr_model"], "-f", str(qa_audio), "-l", "el", "-t", "8",
                   "-bs", "5", "-bo", "5", "-mc", "0", "-sns", "-otxt", "-oj", "-of", str(qa / "whisper")]
        with (qa / "whisper.log").open("w") as log:
            subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True)
        reference = words(text)
        recognized = words((qa / "whisper.txt").read_text())
        distance = word_distance(reference, recognized)
        manifest["quality"] = {"method": "local whisper.cpp large-v3 ASR proxy, not human listening",
               "command": command, "asr_input_wav_sha256": sha(qa_audio),
               "checked_audio_wav_sha256": sha(final), "reference_words": len(reference),
               "recognized_words": len(recognized), "word_distance": distance,
               "wer": round(distance / len(reference), 4),
               "normalization": "alphabetic words; ignore case, punctuation and diacritics", "full_human_listening_review": False}
        save(directory / "manifest.json", manifest)
    print(json.dumps({"dialogue": directory.name, **manifest["result"], "quality": manifest.get("quality")}, ensure_ascii=False), flush=True)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scripts", type=Path, nargs="+")
    parser.add_argument("--ollama-url", default="http://127.0.0.1:11435")
    parser.add_argument("--check-asr", action="store_true")
    parser.add_argument("--ffmpeg", help="Executable path/name; otherwise GREEK_CONTEXT_FFMPEG or PATH")
    parser.add_argument("--whisper-cli", help="Executable path/name; otherwise GREEK_CONTEXT_WHISPER_CLI or PATH")
    parser.add_argument("--asr-model", type=Path, help="Installed Whisper ggml model; otherwise GREEK_CONTEXT_ASR_MODEL")
    args = parser.parse_args()
    try:
        tools = resolve_tools(args.ffmpeg, args.whisper_cli, args.asr_model, args.check_asr)
        load_audio_dependencies()
    except (ValueError, RuntimeError) as error:
        parser.error(str(error))
    endpoint = args.ollama_url.rstrip("/")
    try:
        info = request_json(endpoint + "/api/show", {"model": MODEL})
        if not {"male-greek", "female-greek"}.issubset(info.get("voices", [])):
            raise ValueError(f"Model {MODEL} must expose male-greek and female-greek voices")
        models = request_json(endpoint + "/api/tags")["models"]
        model_digest = next(item["digest"] for item in models if item["name"] == MODEL)
    except (OSError, ValueError, KeyError, TypeError, StopIteration) as error:
        parser.error(f"LFM speech service at {endpoint} is unavailable or incompatible: {error}. "
                     "Configure --ollama-url with a local service exposing /api/show, /api/tags "
                     "and /v1/audio/speech for the required LFM model and Greek voices.")
    for path in args.scripts:
        render(path.resolve(), endpoint, model_digest, args.check_asr, tools)


if __name__ == "__main__":
    main()
