#!/usr/bin/env python3
"""Render an explicitly requested Russian Qwen dialogue with fixed local voices."""

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import time

import mlx.core as mx
from mlx_audio.tts.utils import load_model
import numpy as np
import soundfile as sf


ROOT = Path(__file__).resolve().parents[1]
MODEL = Path.home() / "Downloads/lfm-audio-benchmark-2026-10-30/models/Qwen3-TTS-1.7B-8bit"
FFMPEG = "/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("script", type=Path)
    args = parser.parse_args()
    script_path = args.script.resolve()
    script = json.loads(script_path.read_text())
    if script.get("language") != "russian":
        raise ValueError("This helper is only for explicitly requested Russian audio; Greek uses LFM")
    roles = script["roles"]
    if len(roles) != 2 or len({r["voice"].lower() for r in roles.values()}) != 2:
        raise ValueError("Use two roles with two distinct voices")
    if {t["role"] for t in script["turns"]} != set(roles):
        raise ValueError("Both declared roles must speak")
    if sha(ROOT / script["source_script"]) != script["source_sha256"]:
        raise ValueError("Source changed")
    directory = script_path.parent
    parts = directory / "parts"
    parts.mkdir(exist_ok=True)
    spec = importlib.util.spec_from_file_location("audio_helpers", ROOT / "scripts/synthesize-role-dialogues.py")
    helpers = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helpers)
    model = load_model(MODEL)
    supported = {voice.lower() for voice in model.supported_speakers}
    if not {r["voice"].lower() for r in roles.values()}.issubset(supported):
        raise ValueError("A selected voice is unavailable")
    manifest = {"created_at": datetime.now(timezone.utc).isoformat(),
        "model": "mlx-community/Qwen3-TTS-12Hz-1.7B-CustomVoice-8bit",
        "model_path": str(MODEL), "language": "russian", "local_only": True,
        "script_sha256": sha(script_path), "roles": roles,
        "profile": {"tempo": 1.0, "turn_pause_seconds_before_tempo": 0.35,
                    "loudnorm": "I=-18:TP=-1.5:LRA=11"}, "turns": []}
    assembled = []
    sample_rate = None
    for number, turn in enumerate(script["turns"], 1):
        voice = roles[turn["role"]]["voice"]
        instruct = roles[turn["role"]].get("instruct", "Speak Russian clearly and naturally at a normal conversational pace.")
        if voice.lower() == "ryan":
            instruct = "Speak Russian at a normal conversational pace with clear articulation, a steady natural rhythm and brief natural pauses."
        if number == len(script["turns"]):
            instruct += " Use a warm, playful, gently teasing tone."
        settings = {"voice": voice, "text": turn["text"], "language": "russian",
                    "instruct": instruct, "temperature": 0.8, "top_k": 50, "top_p": 1.0,
                    "repetition_penalty": 1.05, "max_tokens": 512, "seed": 42 + number}
        cache_key = hashlib.sha256(json.dumps(settings, sort_keys=True).encode()).hexdigest()
        path = parts / f"{number:02d}.wav"
        record_path = path.with_suffix(".json")
        if path.exists() and record_path.exists() and (old := json.loads(record_path.read_text())).get("cache_key") == cache_key and old.get("sha256") == sha(path):
            audio, rate = sf.read(path, dtype="float32")
            record = old
        else:
            started = time.monotonic()
            mx.random.seed(settings["seed"])
            print(f"START {number:02d} {voice}: {turn['text']}", flush=True)
            chunks = list(model.generate(text=turn["text"], voice=voice, lang_code="russian", instruct=instruct,
                temperature=0.8, top_k=50, top_p=1.0, repetition_penalty=1.05, max_tokens=512, verbose=False))
            if not chunks or any(c.token_count >= 512 for c in chunks):
                raise RuntimeError(f"No complete audio at turn {number}")
            rate = chunks[0].sample_rate
            audio = np.concatenate([np.asarray(c.audio).reshape(-1) for c in chunks])
            helpers.prepare_turn(audio, rate)
            sf.write(path, audio, rate, subtype="PCM_16")
            record = {"role": turn["role"], "settings": settings, "cache_key": cache_key,
                "file": str(path.relative_to(directory)), "sha256": sha(path), "voice": voice,
                "text": turn["text"], "duration_seconds": round(len(audio) / rate, 3),
                "generation_seconds": round(time.monotonic() - started, 3)}
            save(record_path, record)
        if sample_rate is not None and sample_rate != rate:
            raise RuntimeError("Inconsistent sample rate")
        sample_rate = rate
        if assembled:
            assembled.append(np.zeros(round(rate * 0.35), dtype=np.float32))
        prepared, gain = helpers.prepare_turn(audio, rate)
        assembled.append(prepared)
        manifest["turns"].append({**record, "assembly_gain": round(gain, 5)})
        save(directory / "manifest.json", manifest)
    native = directory / "native-assembled.wav"
    sf.write(native, np.concatenate(assembled), sample_rate, subtype="PCM_16")
    final = directory / (script["file_stem"] + ".wav")
    subprocess.run([FFMPEG, "-nostdin", "-v", "error", "-y", "-i", str(native),
        "-af", "loudnorm=I=-18:TP=-1.5:LRA=11", "-ar", "24000", "-ac", "1", "-c:a", "pcm_s16le", str(final)], check=True)
    mp3 = final.with_suffix(".mp3")
    subprocess.run([FFMPEG, "-nostdin", "-v", "error", "-y", "-i", str(final),
                    "-c:a", "libmp3lame", "-q:a", "2", str(mp3)], check=True)
    audio, rate = sf.read(final, dtype="float32")
    manifest["result"] = {"wav": final.name, "mp3": mp3.name, "wav_sha256": sha(final),
        "mp3_sha256": sha(mp3), "duration_seconds": round(len(audio)/rate, 3),
        "sample_rate": rate, "peak": float(np.max(np.abs(audio)))}
    save(directory / "manifest.json", manifest)
    print(json.dumps(manifest["result"], ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
