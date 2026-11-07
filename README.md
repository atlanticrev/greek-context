# Greek Context

`greek-context` turns a Holst board into structured, local learning evidence and a compact context file for Greek practice in ChatGPT.

## What works in this MVP

- Import a manually exported `.holst` backup.
- Sign in to Holst once in a dedicated Chrome profile.
- Download the latest board backup directly from a Holst board URL.
- Decode Yjs V1/V2 board data into JSON.
- Normalize frames, text, hierarchy, and candidate media URLs.
- Download observed board media at the highest available storage URL.
- Create an analysis queue for Codex.
- Deduplicate repeated text and media by content hash so later syncs queue only new or changed material.
- Build `learner-profile.json`, a compact `chat-context.md`, and ready-to-paste ChatGPT Project instructions from evidence JSONL.

Holst does not publish this backup API. URL sync is therefore best-effort; manual `.holst` import remains the supported fallback.

## Setup

Requirements: Node.js 20+ and Google Chrome.

```bash
npm install
npm run build
```

## Usage

### Recommended: let Codex sync through your existing Chrome

Ask Codex: **“Sync my Greek Holst board.”** Codex uses the already authenticated board tab, clicks **Download board backup**, and runs:

```bash
npm run dev -- import-latest \
  --board-id YOUR_BOARD_ID \
  --name 'Greek lessons'
```

You do not download or select anything manually. See `docs/codex-browser-sync.md`.
The board ID comes from your own Holst URL. Keep personal board metadata in the
ignored `data/local-board.json`; [the example](examples/local-board.example.json)
shows the format. A cloned repository contains no board, vocabulary or login.

### Import a local backup

In Holst, choose **Export → Download backup**, then run:

```bash
npm run dev -- import /path/to/board.holst --board-id greek-lessons
```

### Enable sync from a URL

Sign in once using the utility's isolated Chrome profile:

```bash
npm run dev -- auth
```

Then sync a board:

```bash
npm run dev -- sync "https://app.holst.so/board/BOARD_ID"
```

Use `--headed` if you want to see the sync browser. Use `--skip-assets` to download only the backup and JSON structure.

If Holst rejects the session or changes its private API, export `.holst` manually and use `import`.

### Analyze with Codex

After import or sync, open:

```text
data/boards/<board-id>/analysis/queue.json
```

The incremental queue contains new or changed board text and local image paths.
Repeated text and files are tracked separately by text hash and asset SHA-256, so
Codex does not reopen identical content on every sync. Codex should inspect
educational material, ignore UI graphics and avatars, and write one JSON object
per line to:

```text
data/boards/<board-id>/analysis/evidence.jsonl
```

See `docs/evidence-schema.md` for the schema and inference rules.

Build the final profile:

```bash
npm run dev -- build-profile <board-id>
```

For the simplest setup, add `chat-context.md` to a ChatGPT Project. For traceable evidence, add `learner-profile.json` too. Copy the contents of `chatgpt-project-instructions.md` into the Project instructions field:

```text
data/boards/<board-id>/output/learner-profile.json
data/boards/<board-id>/output/chat-context.md
data/boards/<board-id>/output/chatgpt-project-instructions.md
```

Initialize those uploaded files as the ChatGPT baseline once:

```bash
npm run dev -- init-chatgpt-baseline <board-id>
```

After later lessons, `build-profile` regenerates `chat-context-update.md` as a
small cumulative diff from that baseline. Keep the original two Project sources
and replace only `chat-context-update.md`. When you intentionally upload a new
full profile, run `init-chatgpt-baseline` again to start a fresh empty diff.

The compact Markdown file is intentionally self-contained: it separates practiced material from reading-only exposure and tells ChatGPT how quickly to introduce new Greek.

## Listening reference library

Local whisper.cpp transcripts of the board's audio are kept in
data/listening-reference-library/, with separate texts, source links, review notes,
and a combined context file. The resumable script also adds audio from later imports.
See [the library workflow](docs/listening-reference-library.md) for commands and model settings.
The library stays under private data/ and does not imply confirmed learner proficiency.

Local synthetic versions are stored separately in data/listening-generated/.
See [local dialogue synthesis](docs/listening-synthesis.md) for the voices,
current conversational pace, and quality checks.
Greek synthesis now defaults to LFM3 only. Role-based versions use the Greek male
and female presets, with a fixed voice per role and one assembled recording per source.
New recordings use a normal conversational pace with clear diction and no artificial
slowdown. Ryan's Russian delivery also uses a normal, steady conversational rhythm.
The private catalogue is data/listening-generated/role-dialogues/README.md.
For newly authored practice, use [the recurring generation workflow](docs/listening-practice.md):
one voice for a monologue, exactly two fixed voices for a dialogue, with the studied
topics and vocabulary. New practice lives in data/listening-generated/practice/.

## Data layout

```text
data/boards/<board-id>/
├── raw/
│   ├── backup.holst
│   └── sync-metadata.json
├── normalized/
│   └── board.json
├── assets/
│   ├── manifest.json
│   └── files/
├── analysis/
│   ├── catalog.json
│   ├── analyzed-catalog.json
│   ├── chatgpt-baseline-profile.json
│   ├── queue.json
│   └── evidence.jsonl
└── output/
    ├── learner-profile.json
    ├── chat-context.md
    ├── chat-context-update.md
    └── chatgpt-project-instructions.md
```

All files under `data/` are intentionally ignored by Git, including the local
Greek–Russian vocabulary, listening reference library, browser profile and
generated audio. Board backups (`*.holst`), root `output/`, environment files,
media and personal study plans are ignored too. Import your own authorized board
to populate a new checkout. Do not force-add these private files.

Only the application, tests and reusable documentation belong in the repository.
Share generated `chat-context.md` and `learner-profile.json` separately when you
intend to give someone access to your learning evidence. They are never included
in a normal Git commit.

## Development checks

```bash
npm run typecheck
npm test
npm run build
```

The TypeScript CLI works with Node.js 20+. The optional Python listening tools
are local developer utilities: they require `numpy`, `soundfile`, `ffmpeg`,
`whisper-cli` and separately installed speech models. Greek synthesis calls the
local LFM3 service with `lfm3-audio:2b-q8_0` and its Greek voice presets; it does
not download a model. The legacy Russian Qwen helper additionally imports `mlx`
and `mlx_audio` and rejects Greek scripts. It is separate from the LFM workflow.

The Python utilities retain macOS/Homebrew defaults for executable and model
locations. Review those paths in the scripts before using them on another
machine. `npm install` installs only the TypeScript application's dependencies.
The personal `greek-listening-practice` Codex skill is installed separately under
`~/.codex/skills/` and is not bundled here; the reusable scripts and workflow
documentation are included.
