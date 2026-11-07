# Greek Context

`greek-context` turns an authorized Holst board into local learning evidence, a Greek learner profile and compact ChatGPT context. It also maintains a Greek–Russian Quizlet dictionary and a reviewed source-audio library for creating new listening practice.

## Setup

The TypeScript CLI requires Node.js 20+. The local Python utilities require Python 3.10+. Browser workflows use Google Chrome and the official Google Chrome DevTools tooling configured in the active Codex environment.

```sh
npm install
npm run build
```

A clone includes the shared learning base: the [Greek–Russian dictionary](data/vocabulary/greek-russian.json), normalized Holst material and source assets, evidence and learner context, reviewed audio transcripts, and completed practice texts with MP3 recordings. You can inspect the data and prepare new texts immediately after cloning; updating the online board requires your own authorized login. Models and account sessions are not included. The shared board metadata is in `data/local-board.json`; [the example](examples/local-board.example.json) shows its format for another board.

## Project skills

The canonical workflows live directly in `.agents/skills/`, so Codex can discover them in this project. No personal skill installation is required.

| Skill | What it does | Example request |
| --- | --- | --- |
| [greek-holst-context-sync](.agents/skills/greek-holst-context-sync/SKILL.md) | Exports the latest Holst board, reviews its incremental changes, updates evidence/context and transcribes new source audio into the reference library. | “Update my Greek board and context.” |
| [greek-quizlet-vocabulary](.agents/skills/greek-quizlet-vocabulary/SKILL.md) | Imports complete Quizlet sets with exact-pair deduplication, provenance and explicit editorial corrections. | “Add these Quizlet links to my dictionary.” |
| [greek-listening-practice](.agents/skills/greek-listening-practice/SKILL.md) | Authors new dialogues or monologues on studied material, validates them and renders local LFM audio. | “Create two new dialogues from our studied vocabulary.” |

Invoke a skill by name, for example `$greek-holst-context-sync`, or make the corresponding request. Each skill contains its commands, input schemas, prerequisites and checks. Detailed operational instructions are kept there rather than duplicated in documentation.

Audio transcription requires local `whisper-cli`, `ffmpeg`, `ffprobe` and installed ggml models. Audio rendering additionally needs `numpy`, `soundfile` and an LFM-compatible local speech service with `lfm3-audio:2b-q8_0` and its Greek male/female presets. The repository provides clients, not a speech server or downloaded models. Binary/model paths and the service endpoint are configurable; see the listening skill for the exact contract and options. The legacy comparison/Russian utilities are outside the canonical Greek practice workflow.

## Architecture and shared learning data

The CLI decodes Holst's Yjs V1/V2 backups, normalizes frames/text/media, extracts assets and queues only new or changed content by text hash and asset SHA-256. Codex reviews that material and writes source-linked evidence. The profile builder produces a full profile, compact context and, when a baseline exists, a cumulative ChatGPT update. Board presence means introduced material; completed exercises can support practice, while confirmed proficiency requires a separate assessment.

```text
data/
├── local-board.json
├── boards/<board-id>/
│   ├── raw/
│   ├── normalized/
│   ├── assets/
│   ├── analysis/
│   └── output/
├── vocabulary/
│   ├── greek-russian.json
│   └── quizlet/
├── listening-reference-library/
└── listening-generated/
```

Source audio and reviewed transcripts stay separate from newly generated practice. Every vocabulary card retains its source, even when identical pairs share a dictionary entry. Quizlet captures, source assets and reviewed ASR results are versioned alongside the common base. Existing generated texts remain labeled as generated, and historical render manifests record their original settings.

The `.gitignore` includes the canonical learning directories while excluding browser profiles and credentials, raw `.holst` archives, sync-history copies, model files, working conversions, per-turn audio caches, experiments and local reports. Source images and audio are included so evidence and transcript links work in a clone. Referenced rendered-frame PNGs are also retained under `sync-history/*/rendered-new-frames/`; backup copies under the same history tree stay excluded. Final generated MP3 files are shared; duplicate WAV exports and intermediate turns can be regenerated. Historical manifests may refer to those local render artifacts or record the original machine's executable/model paths; current source and runtime references use repository-relative paths.

Pull the latest changes before updating the shared base, review the learning-data diff, and commit the resulting canonical files together. A shared learner profile records its source learner's evidence and must not be treated as proof of another user's proficiency.

## Development checks

```sh
npm run typecheck
npm test
npm run build
python3 -m unittest discover -s tests -p 'test_*.py'
```

Use `npm run dev -- --help` for CLI commands. The preferred authorized-browser workflow and its local-backup fallback are documented in the Holst skill. The older URL-sync helper depends on Holst's unpublished backup API and remains best-effort.
