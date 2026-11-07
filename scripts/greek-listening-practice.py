#!/usr/bin/env python3
"""Prepare evidence for Codex, validate new Greek texts, and render them locally.

Codex authors the text using the skill; this script does not invent text itself.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import difflib
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import unicodedata

ROOT = Path(__file__).resolve().parents[1]
VOCAB = ROOT / "data/vocabulary/greek-russian.json"
REFERENCES = ROOT / "data/listening-reference-library/generation-references.jsonl"
PRACTICE = ROOT / "data/listening-generated/practice"


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tokens(text):
    return re.findall(r"[^\W\d_]+", unicodedata.normalize("NFC", text).lower())


def comparison_tokens(text):
    return ["".join(c for c in unicodedata.normalize("NFD", word)
                    if unicodedata.category(c) != "Mn") for word in tokens(text)]


def relative(path):
    return str(path.resolve().relative_to(ROOT))


def build_context(output):
    candidates = list((ROOT / "data/boards").glob("*/output/learner-profile.json"))
    if not candidates:
        raise ValueError("Build the learner profile first")
    profile_path = max(candidates, key=lambda p: read(p)["generatedAt"])
    profile = read(profile_path)
    vocabulary = read(VOCAB)
    references = [json.loads(line) for line in REFERENCES.read_text().splitlines() if line.strip()]
    references = [r for r in references if r.get("reference_ready")]
    known = {}
    def index(text, evidence):
        for word in tokens(text):
            if any("\u0370" <= c <= "\u03ff" or "\u1f00" <= c <= "\u1fff" for c in word):
                known.setdefault(word, evidence)
    for entry in vocabulary["entries"]:
        index(entry["greek"], {"kind": "studied_vocabulary", "entry": entry["greek"], "sources": entry["sources"]})
    for ref in references:
        index(ref["text"], {"kind": "reference_text", "id": ref["id"]})
    for skill in profile["skills"]:
        index(skill["label"], {"kind": "profile_label", "skill_id": skill["skillId"]})
        for evidence in skill.get("evidence", []):
            index(evidence.get("observation", ""), {"kind": "profile_evidence", "skill_id": skill["skillId"]})
    context = {"schema_version": 1, "created_at": datetime.now(timezone.utc).isoformat(),
        "inputs": [{"path": relative(p), "sha256": sha(p)} for p in [profile_path, VOCAB, REFERENCES]],
        "learner_estimate": profile["proficiencyEstimate"], "mastery_is_not_assumed": True,
        "skills": profile["skills"], "vocabulary": vocabulary["entries"],
        "references": references, "known_forms": known}
    save(output / "context.json", context)
    lines = ["# Материал для новых текстов по греческому", "",
             "Текущий материал не равен подтверждённому владению языком. Создавать новые ситуации, а не переозвучивать урок.", "",
             "## Темы и грамматика с источниками", ""]
    for skill in profile["skills"]:
        if skill["category"] in {"conversation_topic", "grammar"}:
            lines.append(f"- `{skill['skillId']}` [{skill['status']}]: {skill['label']}")
    lines.extend(["", "## Словарь, пройденный с учителем", ""])
    for entry in vocabulary["entries"]:
        lines.append(f"- {entry['greek']} — {entry['russian']}")
    lines.extend(["", "## Аудиореференсы", ""])
    for ref in references:
        if ref["content_type"] in {"dialogue", "dialogue_collection", "monologue", "descriptions"}:
            lines.extend([f"### {ref['id']} — {ref['title']}", "", ref["text"], ""])
    (output / "context.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"context": relative(output / "context.json"), "vocabulary_entries": len(vocabulary["entries"]),
            "known_surface_forms": len(known), "reference_texts": len(references)}


def validate(draft_path):
    draft = read(draft_path)
    context_path = ROOT / draft["context_path"]
    context = read(context_path)
    errors = []
    for source in context["inputs"]:
        if sha(ROOT / source["path"]) != source["sha256"]:
            errors.append(f"Study source changed; rebuild context: {source['path']}")
    if draft.get("artifact_type") != "generated_practice" or draft.get("text_origin") != "newly_authored":
        errors.append("Label the work as generated_practice / newly_authored")
    kind = draft.get("format")
    stem = draft.get("file_stem", "")
    if not isinstance(stem, str) or len(stem) > 64 or not re.fullmatch(r"(?:dialogue|monologue)-[a-z0-9]+(?:-[a-z0-9]+)*", stem) or not stem.startswith(str(kind) + "-"):
        errors.append("Set a short English file_stem with format and topic, e.g. dialogue-about-coffee")
    roles = draft.get("roles", {})
    voices = {role.get("voice") for role in roles.values()}
    if kind == "monologue":
        if len(roles) != 1 or not voices.issubset({"male-greek", "female-greek"}):
            errors.append("Monologue: exactly one role with one LFM Greek voice")
    elif kind == "dialogue":
        if len(roles) != 2 or voices != {"male-greek", "female-greek"}:
            errors.append("Dialogue: exactly two roles, male-greek and female-greek")
    else:
        errors.append("Format must be monologue or dialogue")
    turns = draft.get("turns", [])
    if not turns or any(t.get("role") not in roles or not t.get("text", "").strip() for t in turns):
        errors.append("Every turn needs a declared role and nonempty text")
    if {t.get("role") for t in turns} != set(roles):
        errors.append("Every role must actually speak")
    text = "\n".join(t.get("text", "") for t in turns)
    if re.search(r"[a-zA-Z]", text):
        errors.append("Use Greek spoken text, with names written in Greek")
    skill_index = {s["skillId"]: s for s in context["skills"]}
    for key, category in [("topic_ids", "conversation_topic"), ("grammar_ids", "grammar")]:
        selected = draft.get(key, [])
        if not selected:
            errors.append(f"Specify {key}")
        for identifier in selected:
            skill = skill_index.get(identifier)
            if not skill or skill["category"] != category or skill["status"] not in {"practiced", "needs_review", "confirmed"}:
                errors.append(f"Use practiced material or explicit revision, not a new skill: {identifier}")
    refs = {r["id"]: r for r in context["references"]}
    if not draft.get("source_reference_ids") or any(r not in refs for r in draft.get("source_reference_ids", [])):
        errors.append("Cite existing reference IDs for style and structures")
    vocabulary = {entry["greek"] for entry in context["vocabulary"]}
    if not draft.get("target_vocabulary") or any(item not in vocabulary for item in draft.get("target_vocabulary", [])):
        errors.append("Target vocabulary must quote actual studied dictionary entries")
    surface = tokens(text)
    known = context["known_forms"]
    reviewed = {}
    for item in draft.get("inflection_reviews", []):
        form = unicodedata.normalize("NFC", item["surface"]).lower()
        lemma = unicodedata.normalize("NFC", item["lemma"]).lower()
        if form not in surface or lemma not in known or not item.get("reason", "").strip():
            errors.append(f"Invalid inflection review: {form}; use an attested lemma and explain the form")
        else:
            reviewed[form] = item
    unresolved = sorted(set(surface) - set(known) - set(reviewed))
    if unresolved:
        errors.append("Unattested words/forms: " + ", ".join(unresolved))
    editorial = draft.get("editorial_review", {})
    if not all(editorial.get(k) is True for k in ["greek_checked", "within_studied_grammar", "new_situation_checked"]):
        errors.append("Codex must review Greek, actual grammar and the new situation before rendering")
    if not editorial.get("notes") or not draft.get("novelty_changes"):
        errors.append("Explain the editorial review and how the situation differs from the references")
    comparisons = []
    candidates = [(r["id"], r["text"]) for r in context["references"]]
    for previous in PRACTICE.glob("**/draft.json"):
        if previous.resolve() != draft_path.resolve():
            old = read(previous)
            candidates.append((relative(previous), "\n".join(t["text"] for t in old.get("turns", []))))
    a = comparison_tokens(text)
    if not a:
        errors.append("Empty spoken text")
    for identifier, original in candidates:
        b = comparison_tokens(original)
        matcher = difflib.SequenceMatcher(a=a, b=b, autojunk=False)
        fraction = sum(block.size for block in matcher.get_matching_blocks()) / max(1, len(a))
        exact = bool(a) and a == b
        if exact or (len(a) >= 20 and fraction >= 0.78):
            errors.append(f"Text is too close to {identifier}: aligned fraction {fraction:.1%}")
        comparisons.append({"reference": identifier, "aligned_fraction": round(fraction, 4),
                            "longest_exact_run_words": matcher.find_longest_match().size})
    comparisons.sort(key=lambda r: r["aligned_fraction"], reverse=True)
    report = {"ok": not errors, "errors": errors, "draft_sha256": sha(draft_path),
        "context_sha256": sha(context_path), "word_count": len(surface),
        "lexical_audit": {"known_form_occurrences": sum(w in known for w in surface),
            "reviewed_inflection_occurrences": sum(w not in known and w in reviewed for w in surface),
            "unresolved_forms": unresolved, "inflection_relations_are_editorially_reviewed_not_automatically_proven": True},
        "novelty_closest": comparisons[:5], "editorial_review": editorial,
        "limits": "Similarity and word-form checks are heuristics; Greek grammar and meaning require the recorded Codex editorial review."}
    save(draft_path.parent / "validation.json", report)
    return draft, report


def render(draft_path, endpoint):
    draft, report = validate(draft_path)
    if not report["ok"]:
        return report
    directory = draft_path.parent
    text_path = directory / "practice.txt"
    text = "\n".join(t["text"] for t in draft["turns"]) + "\n"
    text_path.write_text(text, encoding="utf-8")
    script = {**draft, "authored_text_path": relative(text_path), "authored_text_sha256": sha(text_path),
        "role_assignment_status": "newly authored; explicit fixed voices per role",
        "casting_note": "Новый учебный текст на пройденном материале. " +
            ("Диалог двух персонажей: каждому назначен свой постоянный голос LFM." if draft["format"] == "dialogue" else "Монолог: один постоянный голос LFM."),
        "validation_sha256": sha(directory / "validation.json")}
    save(directory / "script.json", script)
    subprocess.run([sys.executable, str(ROOT / "scripts/synthesize-role-dialogues.py"),
                    str(directory / "script.json"), "--ollama-url", endpoint, "--check-asr"], check=True)
    manifest = read(directory / "manifest.json")
    context = read(ROOT / draft["context_path"])
    skills = {s["skillId"]: s for s in context["skills"]}
    lines = [f"# {draft['title']}", "", "**Новый сгенерированный текст**, а не переозвучка учебного диалога.", "",
             f"[MP3]({manifest['result']['mp3']}) · [WAV]({manifest['result']['wav']}) · [Текст с ролями]({draft['file_stem']}.md)", "",
             "## Материал", ""]
    for key in ["topic_ids", "grammar_ids"]:
        for identifier in draft[key]:
            lines.append(f"- {skills[identifier]['label']} (`{identifier}`, {skills[identifier]['status']}).")
    lines.extend(["", "Целевой словарь: " + ", ".join(draft["target_vocabulary"]), "", "## Что изменено", ""])
    lines.extend("- " + change for change in draft["novelty_changes"])
    lines.extend(["", "Референсы: " + ", ".join(draft["source_reference_ids"]), "",
        f"Проверка словоформ: {report['word_count']} слов, незнакомых неразобранных форм — {len(report['lexical_audit']['unresolved_forms'])}. "
        "Для новых форм известных слов сохранены редакторские пояснения. Это не тест знания ученика.", "",
        f"Whisper large-v3: расхождение слов {manifest['quality']['word_distance']} / {manifest['quality']['reference_words']}. "
        "ASR не заменяет проверку произношения на слух; полная проверка человеком не заявляется.", "",
        "[Проверка текста](validation.json) · [Параметры озвучки](manifest.json)"])
    (directory / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"ok": True, "mp3": relative(directory / manifest["result"]["mp3"]),
            "word_count": report["word_count"], "duration_seconds": manifest["result"]["duration_seconds"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    context_parser = sub.add_parser("context")
    context_parser.add_argument("--output", type=Path, required=True)
    for command in ["validate", "render"]:
        item = sub.add_parser(command)
        item.add_argument("draft", type=Path)
        if command == "render":
            item.add_argument("--ollama-url", default="http://127.0.0.1:11435")
    args = parser.parse_args()
    if args.command == "context":
        result = build_context(args.output.resolve())
    elif args.command == "validate":
        _, result = validate(args.draft.resolve())
    else:
        result = render(args.draft.resolve(), args.ollama_url)
    print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)
    if result.get("ok") is False:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
