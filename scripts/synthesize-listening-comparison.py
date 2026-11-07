#!/usr/bin/env python3
"""Make private, local TTS comparisons from an existing Greek reference text.

Run with the Python environment containing mlx-audio, numpy and soundfile.
Qwen's Greek output is experimental: Greek has no supported language token.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import subprocess
import time
import urllib.request

import numpy as np
import soundfile as sf


ROOT = Path(__file__).resolve().parents[1]
BENCHMARK = Path.home() / "Downloads/lfm-audio-benchmark-2026-10-30"
FFMPEG = "/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg"
PROFILE = {
    "name": "natural-reading-v2",
    "kind": "project preset, not a native model mode",
    "one_request_per_turn": True,
    "pause_between_turns_seconds_before_tempo": 0.35,
    "tempo_multiplier": 1.0,
    "pitch_preserved": True,
    "loudness_filter": "loudnorm=I=-18:TP=-1.5:LRA=11",
    "single_female_narrator_for_both_roles": True,
}


def save_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def audio_check(audio):
    audio = np.asarray(audio, dtype=np.float32)
    if audio.ndim == 2:
        audio = audio.mean(axis=1)
    audio = audio.reshape(-1)
    if not len(audio) or not np.isfinite(audio).all() or np.max(np.abs(audio)) < 1e-5:
        raise RuntimeError("Empty, non-finite or silent generated audio")
    return audio


def trim_padding(audio, sample_rate):
    # Trim only exterior silence, retaining 100 ms on either side of speech.
    audible = np.flatnonzero(np.abs(audio) > 0.003)
    if not len(audible):
        return audio
    padding = int(sample_rate * 0.1)
    return audio[max(0, audible[0] - padding):min(len(audio), audible[-1] + padding + 1)]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--engine", choices=["both", "lfm3", "qwen3", "melina"], default="lfm3")
    parser.add_argument("--qwen-model", type=Path, default=BENCHMARK / "models/Qwen3-TTS-1.7B-8bit")
    parser.add_argument("--qwen-instruct", default="Speak clearly at a normal conversational pace, with natural intonation.")
    parser.add_argument("--qwen-temperature", type=float, default=0.8)
    parser.add_argument("--ollama-url", default="http://127.0.0.1:11435")
    args = parser.parse_args()
    source = args.source.resolve()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    lines = [line.strip() for line in source.read_text(encoding="utf-8").splitlines() if line.strip()]
    removed_heading = lines.pop(0) if lines and lines[0].startswith("Μάθημα ") else None
    text = "\n".join(lines) + "\n"
    text_path = output / "dialogue.txt"
    if text_path.exists() and text_path.read_text(encoding="utf-8") != text:
        raise RuntimeError("Output contains a different dialogue; choose a new directory")
    text_path.write_text(text, encoding="utf-8")
    save_json(output / "source.json", {
        "source_transcript": str(source.relative_to(ROOT)), "source_sha256": digest(source),
        "reference_id": source.stem, "omitted_service_heading": removed_heading,
        "dialogue_sha256": digest(text_path), "turn_count": len(lines),
        "profile": PROFILE, "synthetic_audio_is_not_original_reference": True,
    })

    engines = ["lfm3", "qwen3"] if args.engine == "both" else [args.engine]
    for engine in engines:
        directory = output / "parts" / engine
        directory.mkdir(parents=True, exist_ok=True)
        manifest_path = output / f"{engine}.json"
        manifest = {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "engine": engine, "profile": PROFILE, "dialogue_sha256": digest(text_path),
            "turns": [], "local_only": True,
        }
        model = None
        if engine == "lfm3":
            manifest.update(model="lfm3-audio:2b-q8_0", voice="female-greek", language="el",
                            greek_support="native Greek voice", endpoint=args.ollama_url)
        elif engine == "melina":
            manifest.update(model="macOS local speech synthesis", voice="Melina", language="el_GR",
                            greek_support="native Greek voice", native_rate_words_per_minute="system_default")
        else:
            import mlx.core as mx
            from mlx_audio.tts.utils import load_model
            print("Loading Qwen3-TTS locally", flush=True)
            model = load_model(args.qwen_model)
            manifest.update(
                model="mlx-community/Qwen3-TTS-12Hz-1.7B-CustomVoice-8bit", voice="Serena",
                model_path=str(args.qwen_model), language="auto",
                greek_support="unsupported / experimental",
                instruct=args.qwen_instruct,
                decoding={"temperature": args.qwen_temperature, "top_k": 50, "top_p": 1.0,
                          "repetition_penalty": 1.05, "max_tokens": 512, "seed_base": 42},
            )
        assembled = []
        sample_rate = None
        for number, line in enumerate(lines, start=1):
            part = directory / f"{number:02d}.wav"
            metadata_path = part.with_suffix(".json")
            cache_key = hashlib.sha256(json.dumps({
                "text": line, "model": manifest["model"], "voice": manifest["voice"],
                "model_path": manifest.get("model_path"), "endpoint": manifest.get("endpoint"),
                "instruct": manifest.get("instruct"), "decoding": manifest.get("decoding"),
                "native_rate_words_per_minute": manifest.get("native_rate_words_per_minute"),
            }, sort_keys=True).encode()).hexdigest()
            started = time.monotonic()
            if part.exists() and metadata_path.exists() and json.loads(metadata_path.read_text())["cache_key"] == cache_key:
                audio, rate = sf.read(part, dtype="float32")
                record = json.loads(metadata_path.read_text())
                print(f"REUSED {engine} {number:02d}/{len(lines)}", flush=True)
            else:
                print(f"START {engine} {number:02d}/{len(lines)} {line}", flush=True)
                if engine == "lfm3":
                    request = urllib.request.Request(
                        args.ollama_url + "/v1/audio/speech",
                        data=json.dumps({"model": manifest["model"], "input": line,
                                         "voice": manifest["voice"], "response_format": "wav"}).encode(),
                        headers={"Content-Type": "application/json"},
                    )
                    with urllib.request.urlopen(request, timeout=600) as response:
                        audio, rate = sf.read(io.BytesIO(response.read()), dtype="float32")
                    tokens = None
                elif engine == "melina":
                    input_path = part.with_suffix(".txt")
                    aiff_path = part.with_suffix(".aiff")
                    input_path.write_text(line + "\n", encoding="utf-8")
                    subprocess.run(["/usr/bin/say", "-v", "Melina", "-f", str(input_path),
                                    "-o", str(aiff_path)], check=True)
                    subprocess.run([FFMPEG, "-nostdin", "-v", "error", "-y", "-i", str(aiff_path),
                                    "-ar", "24000", "-ac", "1", "-c:a", "pcm_s16le", str(part)], check=True)
                    audio, rate = sf.read(part, dtype="float32")
                    tokens = None
                else:
                    mx.random.seed(42 + number)
                    chunks = list(model.generate(
                        text=line, voice=manifest["voice"], lang_code="auto",
                        instruct=manifest["instruct"], temperature=args.qwen_temperature, top_k=50, top_p=1.0,
                        repetition_penalty=1.05, max_tokens=512, verbose=False,
                    ))
                    if not chunks:
                        raise RuntimeError(f"No Qwen audio for turn {number}")
                    rate = chunks[0].sample_rate
                    audio = np.concatenate([np.asarray(chunk.audio).reshape(-1) for chunk in chunks])
                    tokens = sum(getattr(chunk, "token_count", 0) for chunk in chunks)
                    if tokens >= 512:
                        raise RuntimeError(f"Qwen reached token limit at turn {number}")
                audio = audio_check(audio)
                sf.write(part, audio, rate, subtype="PCM_16")
                record = {"turn": number, "text": line, "cache_key": cache_key,
                          "file": str(part.relative_to(output)), "sample_rate": rate,
                          "duration_seconds": round(len(audio) / rate, 3),
                          "elapsed_seconds": round(time.monotonic() - started, 3),
                          "generated_tokens": tokens, "sha256": digest(part)}
                save_json(metadata_path, record)
                print(f"DONE {engine} {number:02d} audio={len(audio)/rate:.2f}s elapsed={record['elapsed_seconds']:.1f}s", flush=True)
            audio = audio_check(audio)
            if sample_rate is not None and sample_rate != rate:
                raise RuntimeError("Inconsistent sample rate")
            sample_rate = rate
            if assembled:
                assembled.append(np.zeros(int(rate * PROFILE["pause_between_turns_seconds_before_tempo"]), dtype=np.float32))
            assembled.append(trim_padding(audio, rate))
            manifest["turns"].append(record)
            save_json(manifest_path, manifest)
        assembled_path = output / f"{engine}-native-assembled.wav"
        sf.write(assembled_path, np.concatenate(assembled), sample_rate, subtype="PCM_16")
        final_path = output / f"{engine}-careful.wav"
        subprocess.run([FFMPEG, "-nostdin", "-v", "error", "-y", "-i", str(assembled_path),
                        "-af", PROFILE["loudness_filter"], "-ar", "24000", "-ac", "1",
                        "-c:a", "pcm_s16le", str(final_path)], check=True)
        mp3 = final_path.with_suffix(".mp3")
        subprocess.run([FFMPEG, "-nostdin", "-v", "error", "-y", "-i", str(final_path),
                        "-codec:a", "libmp3lame", "-q:a", "2", str(mp3)], check=True)
        rendered, rendered_rate = sf.read(final_path, dtype="float32")
        rendered = audio_check(rendered)
        manifest["result"] = {"wav": final_path.name, "mp3": mp3.name,
                              "wav_sha256": digest(final_path), "mp3_sha256": digest(mp3),
                              "duration_seconds": round(len(rendered) / rendered_rate, 3),
                              "sample_rate": rendered_rate, "peak": float(np.max(np.abs(rendered))),
                              "rms": float(np.sqrt(np.mean(rendered ** 2)))}
        save_json(manifest_path, manifest)
        print(json.dumps(manifest["result"], ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
