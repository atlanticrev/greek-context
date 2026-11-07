#!/usr/bin/env python3
"""Build the shared, resumable listening-reference library using local whisper.cpp."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time
import unicodedata


ROOT = Path(__file__).resolve().parents[1]
LOCAL_BOARD = ROOT / "data/local-board.json"


def default_board():
    if LOCAL_BOARD.exists():
        return read_json(LOCAL_BOARD).get("boardId")
    return None


def now():
    return datetime.now(timezone.utc).isoformat()


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def normalize_asr_json(path):
    # whisper.cpp can emit individual BPE byte fragments as invalid UTF-8 in
    # token.text, while complete segment.text strings remain valid Greek.
    original = path.read_bytes()
    try:
        result = json.loads(original.decode("utf-8"))
        repaired = False
    except UnicodeDecodeError:
        result = json.loads(original.decode("utf-8", errors="replace"))
        if any("\ufffd" in segment["text"] for segment in result.get("transcription", [])):
            raise RuntimeError(f"Invalid UTF-8 in actual transcript text: {path}")
        path.with_suffix(".json.original-bytes").write_bytes(original)
        save_json(path, result)
        repaired = True
    return result, repaired


def save_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def inventory(board_id, library):
    board_dir = ROOT / "data" / "boards" / board_id
    board = read_json(board_dir / "normalized" / "board.json")
    manifest = read_json(board_dir / "assets" / "manifest.json")
    frames = {frame["id"]: frame.get("label", "") for frame in board["frames"]}
    existing_path = library / "inventory.json"
    existing = read_json(existing_path).get("items", []) if existing_path.exists() else []
    # Other boards and future additions stay in the shared library.
    by_hash = {item["audio_sha256"]: item for item in existing}
    for asset in manifest:
        if not (asset.get("contentType") or "").startswith("audio/"):
            continue
        if asset["status"] != "downloaded" or not asset.get("localPath"):
            raise RuntimeError(f"Audio has not been downloaded: {asset.get('archiveName')}")
        source = board_dir / asset["localPath"]
        digest = sha256(source)
        if digest != asset["sha256"]:
            raise RuntimeError(f"Audio checksum mismatch: {source}")
        name = asset.get("archiveName") or source.name
        related = [obj for obj in board["objects"] if obj.get("raw", {}).get("fileName") == name
                   or any(url.endswith("/" + name) for url in obj.get("assetUrls", []))]
        probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=channels,sample_rate",
                                "-of", "json", str(source)], check=True, text=True, capture_output=True)
        info = json.loads(probe.stdout)
        item = by_hash.get(digest, {"id": "holst-" + source.stem, "audio_sha256": digest, "sources": []})
        occurrences = [{"object_id": obj["id"], "frame_id": obj.get("frameId"),
                        "frame_label": frames.get(obj.get("frameId"), ""),
                        "display_name": obj.get("raw", {}).get("displayFileName", name)} for obj in related]
        source_record = {"board_id": board_id, "snapshot_at": board["generatedAt"],
                         "audio_path": str(source.relative_to(ROOT)), "archive_name": name,
                         "occurrences": occurrences}
        item["sources"] = [record for record in item["sources"] if not
                           (record["board_id"] == board_id and record["archive_name"] == name)] + [source_record]
        item.update({"audio_path": str(source.relative_to(ROOT)), "duration_seconds": float(info["format"]["duration"]),
                     "audio_bytes": source.stat().st_size,
                     "original_titles": sorted({o["display_name"] for s in item["sources"] for o in s["occurrences"]}),
                     "frame_labels": sorted({o["frame_label"] for s in item["sources"] for o in s["occurrences"]})})
        by_hash[digest] = item
    items = sorted(by_hash.values(), key=lambda item: item["id"])
    save_json(existing_path, {"schema_version": 1, "updated_at": now(), "items": items})
    return items


def transcribe(item, library, model, model_name, pass_name, model_hash, vad_model, force):
    identifier = item["id"]
    prefix = library / "raw" / pass_name / identifier
    metadata_path = prefix.with_suffix(".run.json")
    command_options = ["--language", "el", "--threads", "8", "--beam-size", "5", "--best-of", "5",
                       "--temperature", "0", "--output-txt", "--output-srt", "--output-json-full",
                       "--print-progress", "--max-context", "0", "--suppress-nst"]
    if vad_model:
        command_options.extend(["--vad", "--vad-model", str(vad_model), "--vad-threshold", "0.35",
                                "--vad-min-speech-duration-ms", "100", "--vad-min-silence-duration-ms", "300",
                                "--vad-speech-pad-ms", "200"])
    if not force and metadata_path.exists() and prefix.with_suffix(".json").exists():
        previous = read_json(metadata_path)
        if (previous.get("audio_sha256") == item["audio_sha256"] and previous.get("model_sha256") == model_hash
                and previous.get("options") == command_options):
            print(f"REUSED {pass_name} {identifier}", flush=True)
            return
    source = ROOT / item["audio_path"]
    wav = library / "work" / (identifier + ".wav")
    wav.parent.mkdir(parents=True, exist_ok=True)
    if not wav.exists():
        temporary = wav.with_suffix(".partial.wav")
        subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", str(source),
                        "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", str(temporary)], check=True)
        temporary.replace(wav)
    prefix.parent.mkdir(parents=True, exist_ok=True)
    command = ["whisper-cli", "--model", str(model), "--file", str(wav), "--output-file", str(prefix), *command_options]
    started = time.monotonic()
    print(f"START {pass_name} {identifier} audio={item['duration_seconds']:.1f}s titles={item['original_titles']}", flush=True)
    with prefix.with_suffix(".log").open("w", encoding="utf-8") as log:
        subprocess.run(command, check=True, stdout=log, stderr=subprocess.STDOUT)
    result, repaired = normalize_asr_json(prefix.with_suffix(".json"))
    if not result.get("transcription"):
        raise RuntimeError(f"Empty transcript: {identifier}")
    elapsed = time.monotonic() - started
    save_json(metadata_path, {"completed_at": now(), "engine": "whisper.cpp", "model": model_name,
                             "model_path": str(model), "model_sha256": model_hash,
                             "audio_sha256": item["audio_sha256"], "options": command_options,
                             "vad_model_sha256": sha256(vad_model) if vad_model else None,
                             "raw_token_utf8_repaired": repaired,
                             "elapsed_seconds": round(elapsed, 3), "command": command})
    print(f"DONE {pass_name} {identifier} elapsed={elapsed:.1f}s", flush=True)


def clean_text(text):
    text = unicodedata.normalize("NFC", text)
    text = re.sub(r"[ \t]+", " ", text)
    return "\n".join(line.strip() for line in text.splitlines() if line.strip()).strip()


def publish(items, library):
    import difflib
    records = []
    transcript_dir = library / "transcripts"
    transcript_dir.mkdir(parents=True, exist_ok=True)
    for item in items:
        identifier = item["id"]
        primary = library / "raw/primary" / (identifier + ".json")
        if not primary.exists():
            continue
        raw = read_json(primary)
        text = clean_text("\n".join(segment["text"] for segment in raw["transcription"]))
        issues = []
        log_path = primary.with_suffix(".log")
        if log_path.exists():
            detected = [(float(a), float(b)) for a, b in re.findall(
                r"VAD segment \d+: start = ([\d.]+), end = ([\d.]+)", log_path.read_text(errors="replace"))]
            intervals = [(s.get("offsets", {}).get("from", 0) / 1000,
                          s.get("offsets", {}).get("to", 0) / 1000) for s in raw["transcription"]]
            uncovered = sum(max(0, end - start - sum(max(0, min(end, b) - max(start, a))
                                                    for a, b in intervals)) for start, end in detected)
            if uncovered > 2:
                issues.append({"type": "possible_omitted_speech", "uncovered_vad_seconds": round(uncovered, 2)})
        for segment in raw["transcription"]:
            offsets = segment.get("offsets", {})
            if offsets.get("from", 0) > item["duration_seconds"] * 1000 + 500:
                issues.append({"type": "segment_starts_after_audio", "text": segment["text"], "offsets": offsets})
            if offsets.get("to", 0) > item["duration_seconds"] * 1000 + 1000:
                issues.append({"type": "segment_ends_after_audio", "text": segment["text"], "offsets": offsets})
        tokens = [token for segment in raw["transcription"] for token in segment.get("tokens", [])
                  if token.get("text", "").strip() and not token.get("text", "").startswith("[_")]
        low = [token for token in tokens if token.get("p", 1) < .35]
        if low:
            issues.append({"type": "low_token_probability", "count": len(low),
                           "tokens": [{"text": token.get("text"), "p": token.get("p"),
                                       "timestamps": token.get("timestamps")} for token in low]})
        if re.search(r"[А-Яа-яЁё]", text):
            issues.append({"type": "non_greek_cyrillic_text"})
        for phrase in ["Υπότιτλοι", "AUTHORWAVE", "Σας ευχαριστούμε που παρακολουθήσατε"]:
            if phrase.casefold() in text.casefold():
                issues.append({"type": "possible_hallucination", "text": phrase})
        repeated = [line for line, count in Counter(text.splitlines()).items() if count >= 3 and len(line) > 20]
        if repeated:
            issues.append({"type": "repetition_check", "lines": repeated})
        control = library / "raw/control-vad" / (identifier + ".json")
        if not control.exists():
            control = library / "raw/control" / (identifier + ".json")
        comparison = None
        if control.exists():
            control_text = clean_text("\n".join(segment["text"] for segment in read_json(control)["transcription"]))
            def words(value):
                value = "".join(c for c in unicodedata.normalize("NFD", value.casefold()) if not unicodedata.combining(c))
                return re.findall(r"\w+", value)
            similarity = difflib.SequenceMatcher(None, words(text), words(control_text), autojunk=False).ratio()
            comparison = {"method": "normalized_word_sequence_similarity", "similarity": round(similarity, 4),
                          "control_path": str(control.relative_to(ROOT)),
                          "control_text": control_text}
            if similarity < .90:
                issues.append({"type": "cross_decode_difference", "similarity": round(similarity, 4)})
        review_path = library / "reviews" / (identifier + ".json")
        review = read_json(review_path) if review_path.exists() else {"status": "automatic_transcript", "notes": []}
        if review.get("audio_sha256") and review["audio_sha256"] != item["audio_sha256"]:
            raise RuntimeError(f"Review refers to another audio: {identifier}")
        if review.get("primary_json_sha256") and review["primary_json_sha256"] != sha256(primary):
            raise RuntimeError(f"Review is stale after retranscription: {identifier}")
        if "text" in review:
            text = clean_text(review["text"])
        text_path = transcript_dir / (identifier + ".txt")
        text_path.write_text(text + "\n", encoding="utf-8")
        title = review.get("title") or " / ".join(item["original_titles"]) or identifier
        primary_run = read_json(primary.with_suffix(".run.json"))
        record = {**item, "title": title, "language": "el", "text": text,
                  "transcript_path": str(text_path.relative_to(ROOT)), "reference_type": "source_audio_transcript",
                  "model": primary_run["model"], "review": review, "automatic_checks": issues,
                  "content_type": review.get("content_type", "unclassified"),
                  "reference_ready": review.get("reference_ready", False),
                  "comparison": comparison, "raw_primary_path": str(primary.relative_to(ROOT))}
        records.append(record)
        relative_audio = os.path.relpath(ROOT / item["audio_path"], transcript_dir)
        relative_raw = os.path.relpath(primary, transcript_dir)
        relative_srt = os.path.relpath(primary.with_suffix(".srt"), transcript_dir)
        duration = item["duration_seconds"]
        notes = "\n".join("- " + note for note in review.get("notes", [])) or "- Отдельная проверка по слуху не подтверждена."
        evidence_paths = review.get("source_images", []) + review.get("supplementary_asr_paths", [])
        evidence_links = []
        for evidence in evidence_paths:
            evidence_path = Path(evidence)
            if not evidence_path.is_absolute():
                evidence_path = ROOT / evidence_path
            evidence_links.append(f"- [{evidence_path.name}]({os.path.relpath(evidence_path, transcript_dir)})")
        evidence_section = "\n\n## Материалы для сверки\n\n" + "\n".join(evidence_links) + "\n" if evidence_links else ""
        markdown = (f"# {title}\n\n"
                    f"- ID: {identifier}\n- Язык: греческий.\n- Длительность: {duration:.2f} с.\n"
                    f"- Исходные названия: {'; '.join(item['original_titles'])}.\n"
                    f"- Фреймы Holst: {'; '.join(item['frame_labels'])}.\n"
                    f"- Модель: {primary_run['model']}, локальный whisper.cpp.\n"
                    f"- Статус проверки: {review['status']}.\n"
                    f"- Тип материала: {review.get('content_type', 'unclassified')}.\n"
                    f"- [Аудио]({relative_audio}) · [TXT](./{identifier}.txt) · [Исходные ASR-таймкоды SRT]({relative_srt}) · [Исходный JSON]({relative_raw}).\n\n"
                    f"## Текст\n\n{text}\n\n## Проверка и ограничения\n\n{notes}\n\n"
                    "Автоматические сигналы приведены в manifest.json; вероятность токена не является гарантией правильности. "
                    "Учебное аудио служит референсом и не доказывает владение материалом учеником.\n" + evidence_section)
        (transcript_dir / (identifier + ".md")).write_text(markdown, encoding="utf-8")
    save_json(library / "manifest.json", {"schema_version": 1, "updated_at": now(), "count": len(records),
                                          "total_duration_seconds": sum(item["duration_seconds"] for item in records),
                                          "items": records})
    corpus_records = [{key: record[key] for key in ["id", "title", "language", "text", "content_type", "reference_ready",
                       "duration_seconds", "audio_path", "audio_sha256", "transcript_path", "sources", "reference_type"]}
                      | {"review_status": record["review"]["status"], "notes": record["review"].get("notes", [])}
                      for record in records]
    (library / "corpus.jsonl").write_text("".join(json.dumps(record, ensure_ascii=False) + "\n" for record in corpus_records), encoding="utf-8")
    (library / "generation-references.jsonl").write_text("".join(json.dumps(record, ensure_ascii=False) + "\n"
                                                      for record in corpus_records if record["reference_ready"]), encoding="utf-8")
    index = ["# Библиотека аудиореференсов по греческому", "", f"Расшифровано записей: {len(records)}.", "",
             "Тексты учебных аудио, а не образцы подтверждённого владения ученика. Статус проверки указан отдельно.", "",
             "| Название | Время | Тип | Статус |", "| --- | ---: | --- | --- |"]
    context = ["# Дополнительный контекст: исходные аудиореференсы", "",
               "Это расшифровки учебных записей. Наличие материала не означает, что ученик умеет его использовать. "
               "При генерации похожих текстов учитывать статус проверки и отмеченные сомнения. "
               "Сгенерированные варианты сохранять отдельно от исходных транскрипций.", ""]
    for item in records:
        identifier = item["id"]
        index.append(f"| [{item['title'].replace('|', '/')}](./transcripts/{identifier}.md) | {item['duration_seconds']:.1f} с | {item['content_type']} | {item['review']['status']} |")
        context.extend([f"## {item['title']}", "", f"Источник: {identifier}; проверка: {item['review']['status']}.", ""])
        if item["review"].get("notes"):
            context.append("Замечания: " + " ".join(item["review"]["notes"]))
            context.append("")
        context.extend([item["text"], ""])
    (library / "index.md").write_text("\n".join(index) + "\n", encoding="utf-8")
    (library / "context.md").write_text("\n".join(context) + "\n", encoding="utf-8")
    print(f"PUBLISHED count={len(records)} library={library}", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--board-id", default=default_board(),
                        help="Board ID; defaults to shared data/local-board.json")
    parser.add_argument("--library", type=Path, default=ROOT / "data/listening-reference-library")
    parser.add_argument("--model", type=Path)
    parser.add_argument("--model-name", default="large-v3")
    parser.add_argument("--pass-name", choices=["primary", "control", "control-vad"], default="primary")
    parser.add_argument("--vad-model", type=Path,
                        default=Path.home() / "Library/Caches/greek-context/whisper.cpp/ggml-silero-v6.2.0.bin")
    parser.add_argument("--no-vad", action="store_true", help="Useful for a deliberately different control pass")
    parser.add_argument("--only", action="append", default=[])
    parser.add_argument("--limit", type=int)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--publish-only", action="store_true")
    args = parser.parse_args()
    if not args.board_id:
        parser.error("Pass --board-id or configure shared data/local-board.json")
    library = args.library.resolve()
    library.mkdir(parents=True, exist_ok=True)
    items = inventory(args.board_id, library)
    selected = [item for item in items if not args.only or item["id"] in args.only]
    if args.limit is not None:
        selected = selected[:args.limit]
    if not args.publish_only:
        for executable in ["whisper-cli", "ffmpeg", "ffprobe"]:
            if not shutil.which(executable):
                parser.error(f"Missing executable: {executable}")
        if not args.model or not args.model.is_file():
            parser.error("--model must refer to an existing ggml model")
        if not args.no_vad and not args.vad_model.is_file():
            parser.error("--vad-model must refer to an existing Silero ggml model")
        model_hash = sha256(args.model)
        for index, item in enumerate(selected, 1):
            print(f"PROGRESS {index}/{len(selected)}", flush=True)
            transcribe(item, library, args.model.resolve(), args.model_name, args.pass_name, model_hash,
                       None if args.no_vad else args.vad_model.resolve(), args.force)
    publish(items, library)


if __name__ == "__main__":
    main()
