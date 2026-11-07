#!/usr/bin/env python3
"""Merge complete, locally captured Quizlet sets into the private Greek/Russian dictionary.

This command reads saved JSON only. Capture the rendered cards separately through
the user's authorized browser; it does not fetch Quizlet or automate verification.
"""

from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import unicodedata
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]


def normalized(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Greek and Russian text must be nonempty strings")
    return unicodedata.normalize("NFC", value.strip())


def pair(record):
    return normalized(record["greek"]), normalized(record["russian"])


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def capture(path, metadata=None):
    """Read the current capture schema, or historical el/ru-side snapshots."""
    raw = read(path)
    identifier = str(raw.get("id", raw.get("set_id", "")))
    if not identifier.isdecimal():
        raise ValueError(f"Invalid Quizlet set ID: {path}")
    url = raw.get("url", "")
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in {"quizlet.com", "www.quizlet.com"} or identifier not in parsed.path.split("/"):
        raise ValueError(f"URL does not identify Quizlet set {identifier}")
    if "cards" in raw:
        rows = [{"row": item["row"], "greek": item["greek"], "russian": item["russian"]}
                for item in raw["cards"]]
    else:
        rows = []
        for item in raw["rows"]:
            sides = item["sides"]
            if len(sides) != 2 or {side["language"] for side in sides} != {"el", "ru"}:
                raise ValueError(f"Ambiguous Greek/Russian sides in {identifier}")
            texts = {side["language"]: side["text"] for side in sides}
            rows.append({"row": item["source_row"], "greek": texts["el"], "russian": texts["ru"]})
    counts = metadata if metadata is not None else raw
    expected = counts.get("card_count")
    if (type(expected) is not int or expected <= 0 or counts.get("complete") is not True
            or counts.get("extracted_card_count") != expected or len(rows) != expected):
        raise ValueError(f"Set {identifier} is incomplete or lacks verified rendered-UI counts")
    if metadata is not None and any(key in raw and raw[key] != counts[key]
                                    for key in ("card_count", "extracted_card_count", "complete")):
        raise ValueError(f"Capture and source completeness metadata disagree for {identifier}")
    if any(type(row["row"]) is not int for row in rows) or sorted(row["row"] for row in rows) != list(range(1, expected + 1)):
        raise ValueError(f"Set {identifier} rows must cover 1..{expected} exactly once")
    for row in rows:
        pair(row)
    if not raw.get("title") or not raw.get("extracted_at"):
        raise ValueError(f"Set {identifier} needs a title and extraction timestamp")
    return {"id": identifier, "title": raw["title"], "url": url,
            "extracted_at": raw["extracted_at"], "card_count": expected,
            "extracted_card_count": expected, "complete": True}, sorted(rows, key=lambda row: row["row"])


def original_matches(entry, source, row):
    # Historical corrections were entry-wide. New corrections are scoped to a
    # source row so adding provenance cannot silently change another source.
    alternatives = {field: {normalized(entry[field])} for field in ("greek", "russian")}
    if "source_translation" in entry:
        alternatives["russian"].add(normalized(entry["source_translation"]))
    corrections = entry.get("corrections", [])
    for correction in reversed(corrections):
        if correction.get("source_set_id", source["set_id"]) != source["set_id"]:
            continue
        if correction.get("source_row", source["row"]) != source["row"]:
            continue
        field = correction["field"]
        if normalized(correction["corrected"]) in alternatives[field]:
            alternatives[field].add(normalized(correction["original"]))
    return all(normalized(row[field]) in alternatives[field] for field in alternatives)


def validate(dictionary, directory):
    if dictionary.get("schema_version") != 1:
        raise ValueError("Only vocabulary schema_version 1 is supported")
    sources = {str(source["id"]): source for source in dictionary["sources"]}
    if len(sources) != len(dictionary["sources"]):
        raise ValueError("Duplicate source set IDs")
    rows, checks = {}, []
    for identifier, source in sources.items():
        snapshot = (directory / source["snapshot_path"]).resolve()
        if not snapshot.is_relative_to(directory.resolve()):
            raise ValueError("Snapshots must stay inside the private vocabulary directory")
        metadata, captured = capture(snapshot, source)
        if metadata["id"] != identifier:
            raise ValueError("Snapshot and dictionary source IDs differ")
        for row in captured:
            rows[(identifier, row["row"])] = row
        checks.append({"id": identifier, "cards": len(captured), "snapshot_sha256": digest(snapshot)})
    linked, pairs = Counter(), set()
    unique_per_source = {identifier: set() for identifier in sources}
    for entry in dictionary["entries"]:
        key = pair(entry)
        if key in pairs:
            raise ValueError(f"Duplicate normalized dictionary pair: {key[0]}")
        pairs.add(key)
        if not entry.get("sources"):
            raise ValueError("Every entry must cite at least one source row")
        for source in entry["sources"]:
            key = (str(source["set_id"]), source["row"])
            if key not in rows:
                raise ValueError(f"Orphan source row: {key}")
            linked[key] += 1
            if not original_matches(entry, source, rows[key]):
                raise ValueError(f"Source text cannot be reconstructed: {key}")
            unique_per_source[key[0]].add(pair(entry))
    if set(linked) != set(rows) or any(count != 1 for count in linked.values()):
        raise ValueError("Every captured source row must be represented exactly once")
    for identifier, source in sources.items():
        if source.get("unique_pair_count") != len(unique_per_source[identifier]):
            raise ValueError(f"Incorrect unique_pair_count for {identifier}")
    summary = {"source_sets": len(sources), "source_cards": len(rows), "entries": len(pairs),
               "duplicate_cards_merged": len(rows) - len(pairs),
               "corrected_entries": sum(bool(entry.get("corrections")) for entry in dictionary["entries"]),
               "number_translations_added": sum("source_translation" in entry for entry in dictionary["entries"]),
               "complete": True}
    return {"valid": True, "all_source_cards_represented_exactly_once": True,
            "source_text_reconstructable_for_all_cards": True, "summary": summary, "sources": checks}


def merge(dictionary, snapshots, directory, corrections=()):
    result = deepcopy(dictionary)
    known = {str(source["id"]): source for source in result["sources"]}
    by_pair = {pair(entry): entry for entry in result["entries"]}
    edits = {}
    for correction in corrections:
        key = (str(correction["set_id"]), correction["row"], correction["field"])
        if (key in edits or correction["field"] not in {"greek", "russian"}
                or not correction.get("reason")):
            raise ValueError("Corrections need a unique set/row/field and an editorial reason")
        normalized(correction["original"])
        normalized(correction["corrected"])
        edits[key] = correction
    used, processed = set(), set()
    for snapshot in snapshots:
        metadata, rows = capture(snapshot)
        identifier = metadata["id"]
        if identifier in processed:
            raise ValueError(f"Repeated snapshot for set {identifier}")
        processed.add(identifier)
        if identifier in known:
            _, previous = capture(directory / known[identifier]["snapshot_path"], known[identifier])
            if [(r["row"], pair(r)) for r in rows] != [(r["row"], pair(r)) for r in previous]:
                raise ValueError(f"Set {identifier} changed since import; review the revision separately")
            # Repeating a completed import is a no-op, including its review file.
            for key, correction in edits.items():
                if key[0] == identifier:
                    entry = next(e for e in result["entries"] if {"set_id": identifier, "row": key[1]} in e["sources"])
                    if normalized(entry[key[2]]) != normalized(correction["corrected"]):
                        raise ValueError("Review would modify an existing entry; handle it explicitly")
                    used.add(key)
            continue
        try:
            metadata["snapshot_path"] = str(snapshot.resolve().relative_to(directory.resolve()))
        except ValueError as error:
            raise ValueError("Put captures under the private vocabulary directory before importing") from error
        unique = set()
        for row in rows:
            canonical = {field: normalized(row[field]) for field in ("greek", "russian")}
            row_edits = []
            for field in canonical:
                key = (identifier, row["row"], field)
                if key not in edits:
                    continue
                correction = edits[key]
                if normalized(correction["original"]) != canonical[field]:
                    raise ValueError(f"Correction original does not match captured source row {key}")
                canonical[field] = normalized(correction["corrected"])
                row_edits.append({k: v for k, v in correction.items() if k not in {"set_id", "row"}}
                                 | {"source_set_id": identifier, "source_row": row["row"]})
                used.add(key)
            key = pair(canonical)
            unique.add(key)
            if key not in by_pair:
                entry = {**canonical, "sources": []}
                result["entries"].append(entry)
                by_pair[key] = entry
            entry = by_pair[key]
            entry["sources"].append({"set_id": identifier, "row": row["row"]})
            if row_edits:
                entry.setdefault("corrections", []).extend(row_edits)
        metadata["unique_pair_count"] = len(unique)
        metadata["learning_context"] = {"evidence_level": "introduced", "mastery_assessed": False}
        result["sources"].append(metadata)
        known[identifier] = metadata
    if set(edits) != used:
        raise ValueError("Correction refers to a set or row not in this import")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshots", nargs="*", type=Path)
    parser.add_argument("--dictionary", type=Path, default=ROOT / "data/vocabulary/greek-russian.json")
    parser.add_argument("--corrections", type=Path, help="JSON array of reviewed set_id/row/field corrections")
    parser.add_argument("--dry-run", action="store_true", help="Validate and preview without writing any files")
    parser.add_argument("--validate-only", action="store_true", help="Check dictionary and every raw source without writing")
    args = parser.parse_args()
    try:
        if args.validate_only and (args.snapshots or args.corrections):
            raise ValueError("--validate-only does not accept snapshots or corrections")
        if not args.validate_only and not args.snapshots:
            raise ValueError("Pass at least one captured snapshot, or use --validate-only")
        dictionary_path = args.dictionary.resolve()
        directory = dictionary_path.parent
        if args.validate_only and not dictionary_path.exists():
            raise ValueError("Dictionary does not exist")
        if dictionary_path.exists():
            previous = read(dictionary_path)
            validate(previous, directory)
        else:
            previous = {"schema_version": 1, "title": "Greek–Russian vocabulary", "languages": ["el", "ru"],
                        "created_at": datetime.now(timezone.utc).isoformat(),
                        "learning_context": {"evidence_level": "introduced", "mastery_assessed": False},
                        "sources": [], "entries": []}
        if args.validate_only:
            print(json.dumps(validate(previous, directory), ensure_ascii=False, indent=2))
            return
        reviews = read(args.corrections) if args.corrections else []
        result = merge(previous, args.snapshots, directory, reviews)
        report = validate(result, directory)
        changed = result != previous
        report.update({"changed": changed, "dry_run": args.dry_run,
                       "new_entries": len(result["entries"]) - len(previous["entries"]),
                       "new_sets": len(result["sources"]) - len(previous["sources"])})
        if changed and not args.dry_run:
            stamp = datetime.now(timezone.utc)
            result["summary"] = report["summary"]
            result["updated_at"] = stamp.isoformat()
            if dictionary_path.exists():
                backup = directory / "quizlet/history" / f"greek-russian-{stamp.strftime('%Y%m%dT%H%M%S%fZ')}.json"
                backup.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(dictionary_path, backup)
            save(dictionary_path, result)
            save(directory / "quizlet/sources.json", [{key: source[key] for key in ("id", "title", "url")} for source in result["sources"]])
            save(directory / "quizlet/validation.json", report)
        print(json.dumps(report, ensure_ascii=False, indent=2))
    except (ValueError, KeyError, TypeError, OSError) as error:
        parser.exit(1, f"Quizlet import failed: {error}\n")


if __name__ == "__main__":
    main()
