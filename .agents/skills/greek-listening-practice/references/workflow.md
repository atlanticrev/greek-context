# Portable local practice workflow

Run from the repository root. A clone includes the current shared vocabulary, learner evidence and reviewed source library. Pull the latest base before creating practice; use the board-sync and Quizlet skills to add new material:

- `data/boards/*/output/learner-profile.json`: the helper selects the latest `generatedAt`.
- `data/vocabulary/greek-russian.json`: studied words/phrases and provenance; consult each source's evidence level.
- `data/listening-reference-library/generation-references.jsonl`: reviewed reference texts marked ready, not drafts to re-record.

## Runtime prerequisites

Context and validation require Python 3.10+ and its standard library. Rendering also needs `numpy` and `soundfile` in the selected Python environment (`python3 -m pip install numpy soundfile`), ffmpeg, whisper.cpp's `whisper-cli`, a local multilingual large-v3 ggml model and a running **LFM-compatible local speech service**. `npm install` does not install those tools or models, and this repository contains the client, not the speech server.

The service must provide model `lfm3-audio:2b-q8_0` with both Greek presets and these APIs:

- `POST /api/show`: top-level `voices` containing `male-greek` and `female-greek`.
- `GET /api/tags`: installed model names and digests.
- `POST /v1/audio/speech`: `model`, `voice`, `input`, `response_format: wav`, returning WAV bytes.

The default endpoint is `http://127.0.0.1:11435`; use `--ollama-url` for another local endpoint (the flag name is retained for compatibility). Stock Ollama's compatibility with this speech contract is not assumed. Reuse an existing compatible service; do not restart/install one or change models as an unrequested side effect.

Pass `--ffmpeg /path/to/ffmpeg`, `--whisper-cli /path/to/whisper-cli` and `--asr-model /path/to/ggml-large-v3.bin` on `render`, or set `GREEK_CONTEXT_FFMPEG`, `GREEK_CONTEXT_WHISPER_CLI`, `GREEK_CONTEXT_ASR_MODEL`. PATH/default discovery and optional macOS fallbacks are conveniences, not cross-machine requirements. See the helper's `render --help` for current options.

## Prepare and author

Choose a fresh descriptive batch directory:

```sh
python3 scripts/greek-listening-practice.py context \
  --output data/listening-generated/practice/my-batch/context
```

Read the generated `context.md`; `context.json` contains the profile, full dictionary, references, known forms and input hashes. Rebuild it if its source files change.

Write a genuinely new `draft.json` in the batch's piece directory using this schema:

| Field | Required value/meaning |
| --- | --- |
| `schema_version` | `2` |
| `artifact_type`, `text_origin` | `generated_practice`, `newly_authored` |
| `id`, `title` | Unique ID and an unspoken title. |
| `format` | `monologue` or `dialogue`. |
| `file_stem` | English kebab-case format/topic, e.g. `dialogue-about-coffee`; no extension. |
| `context_path` | Project-relative path to this batch's context JSON. |
| `topic_ids`, `grammar_ids` | Actual profile IDs with `practiced`, `needs_review` or `confirmed` status. |
| `source_reference_ids` | Actual reviewed reference IDs used for structure/style. |
| `target_vocabulary` | Complete `greek` field values copied from the dictionary; actually used, including justified inflections. |
| `novelty_changes` | Array explaining changed situation, communicative purpose and facts. |
| `roles` | Role ID → label and fixed Greek voice. |
| `turns` | Ordered objects with `role`, Greek `text` and optional `scene`. |
| `inflection_reviews` | Array of `surface`, attested `lemma`, genuine linguistic `reason`. |
| `editorial_review` | `greek_checked`, `within_studied_grammar`, `new_situation_checked` and substantive `notes`. |

Dialogue role/turn structure:

```json
{
  "roles": {
    "petros": {"label": "Πέτρος", "voice": "male-greek"},
    "eleni": {"label": "Ελένη", "voice": "female-greek"}
  },
  "turns": [
    {"role": "petros", "text": "Καλημέρα!"},
    {"role": "eleni", "text": "Γεια σου!"}
  ]
}
```

This excerpt illustrates roles only; author the full draft using the table. For a monologue, declare exactly one narrator with either Greek voice. Every declared role must speak. Consecutive sentences by one character stay one turn; do not blindly alternate transcript lines or add three characters sharing two voices.

An inflection review applies only if its surface occurs in the new text, for example `{"surface":"μαθαίνει","lemma":"μαθαίνω","reason":"Third-person singular present of an attested type-A verb."}`. Do not use these reviews to disguise a new lexical item. Set editorial flags true only after actually checking the text.

## Validate, render and inspect

```sh
python3 scripts/greek-listening-practice.py validate \
  data/listening-generated/practice/my-batch/my-dialogue/draft.json

python3 scripts/greek-listening-practice.py render \
  data/listening-generated/practice/my-batch/my-dialogue/draft.json \
  --asr-model /path/to/ggml-large-v3.bin
```

Run `render` with the Python where `numpy`/`soundfile` are installed; explicit binary flags or environment variables may also be needed. Validation writes `validation.json` and exits nonzero on unresolved errors. It checks role counts/voices, known forms, source IDs/evidence statuses, input hashes, and similarity to references/previous drafts. Exact duplicates and 20+ word texts with aligned fractions at least 0.78 are rejected. These are useful signals, not proof of grammatical or semantic quality.

Rendering revalidates, writes `practice.txt` and `script.json`, calls the shared LFM engine and exports MP3/WAV/TXT/Markdown with the same `file_stem`. Source hashes, role mappings, separate turns, montage intervals and ASR logs remain alongside the output. The current assembly uses natural brief turn pauses, protected speech edges, fades and bounded loudness adjustment followed by loudnorm. Tempo stays 1.0; no slowing filter or slow-reading prompt is applied.

Read `qa/whisper.txt`, manifest and logs. Investigate substantive mismatches without endless retries for a metric. Names and homophones may differ in ASR spelling. Do not imply a human/native-speaker listening check unless it happened.

The batch README explains vocabulary, sources, changed situation and checks. Deliver each audio with the full Greek role-labeled transcript directly below it, plus matching text links. New practice lives in `data/listening-generated/practice/`; historical source rereadings remain under `data/listening-generated/role-dialogues/` and are never relabeled as new exercises. Share the reviewed drafts, context snapshots, texts, final MP3 files and JSON/text checks. WAV exports, per-turn audio and temporary conversions are local artifacts; historical manifests can retain their recorded paths and hashes. Keep playable Markdown links pointed at files included in the shared base.
