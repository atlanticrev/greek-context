# Greek Context

`greek-context` turns an authorized Holst board into local learning evidence, a Greek learner profile and compact ChatGPT context. It also maintains a Greek–Russian Quizlet dictionary and a reviewed source-audio library for creating new listening practice.

## Setup

The TypeScript CLI requires Node.js 20+. The local Python utilities require Python 3.10+. Browser workflows use Google Chrome and the official Google Chrome DevTools tooling configured in the active Codex environment.

```sh
npm install
npm run build
```

A clone contains application code and skills, not another person's board, vocabulary, audio, models or login. Import your own authorized material. Board metadata belongs in ignored `data/local-board.json`; [the example](examples/local-board.example.json) shows its format.

## Project skills

The canonical workflows live directly in `.agents/skills/`, so Codex can discover them in this project. No personal skill installation is required.

| Skill | What it does | Example request |
| --- | --- | --- |
| [greek-holst-context-sync](.agents/skills/greek-holst-context-sync/SKILL.md) | Exports the latest Holst board, reviews its incremental changes, updates evidence/context and transcribes new source audio into the reference library. | “Update my Greek board and context.” |
| [greek-quizlet-vocabulary](.agents/skills/greek-quizlet-vocabulary/SKILL.md) | Imports complete Quizlet sets with exact-pair deduplication, provenance and explicit editorial corrections. | “Add these Quizlet links to my dictionary.” |
| [greek-listening-practice](.agents/skills/greek-listening-practice/SKILL.md) | Authors new dialogues or monologues on studied material, validates them and renders local LFM audio. | “Create two new dialogues from our studied vocabulary.” |

Invoke a skill by name, for example `$greek-holst-context-sync`, or make the corresponding request. Each skill contains its commands, input schemas, prerequisites and checks. Detailed operational instructions are kept there rather than duplicated in documentation.

Audio transcription requires local `whisper-cli`, `ffmpeg`, `ffprobe` and installed ggml models. Audio rendering additionally needs `numpy`, `soundfile` and an LFM-compatible local speech service with `lfm3-audio:2b-q8_0` and its Greek male/female presets. The repository provides clients, not a speech server or downloaded models. Binary/model paths and the service endpoint are configurable; see the listening skill for the exact contract and options. The legacy comparison/Russian utilities are outside the canonical Greek practice workflow.

## Architecture and private data

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

Source audio and reviewed transcripts stay separate from newly generated practice. Every vocabulary card retains its source, even when identical pairs share a dictionary entry. Original backups, captures and ASR results remain available locally for inspection.

Everything under `data/` is private and ignored by Git, as are `*.holst` backups, root `output/`, media, environment files and personal study plans. Only the application, tests, examples and reusable skills belong in this repository. Do not force-add personal files. Share generated `chat-context.md` and `learner-profile.json` separately when you intend to give someone access to your learning evidence.

## Development checks

```sh
npm run typecheck
npm test
npm run build
python3 -m unittest discover -s tests -p 'test_*.py'
```

Use `npm run dev -- --help` for CLI commands. The preferred authorized-browser workflow and its local-backup fallback are documented in the Holst skill. The older URL-sync helper depends on Holst's unpublished backup API and remains best-effort.
