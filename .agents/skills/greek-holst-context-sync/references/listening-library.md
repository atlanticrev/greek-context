# New source audio and the reviewed reference library

The shared library is `data/listening-reference-library/`. Original audio stays in the board's versioned `assets/files/`; the library stores repository-relative paths, checksums and every Holst occurrence rather than duplicating media. SHA-256 identifies identical audio across imports/boards. Commit reviewed transcripts, reviews, catalog and raw ASR JSON/TXT/SRT together; working WAV conversions, diagnostic experiments and logs remain local.

## Local prerequisites and commands

Install `whisper-cli` from [whisper.cpp](https://github.com/ggml-org/whisper.cpp), `ffmpeg` and `ffprobe` on `PATH`, plus compatible multilingual ggml models. Set `ASR_PRIMARY_MODEL` to a local large-v3 model, `ASR_CONTROL_MODEL` to large-v3-turbo and `ASR_VAD_MODEL` to the Silero VAD model. The script's macOS cache defaults are optional; explicit paths work on other machines. Model sources and checksums are listed in [whisper.cpp's model documentation](https://github.com/ggml-org/whisper.cpp/blob/master/models/README.md). These scripts do not install/download models.

Refresh inventory and publish existing completed transcripts without synthesis or ASR:

```sh
python3 scripts/transcribe-listening.py --board-id "$BOARD_ID" --publish-only
```

Compare `inventory.json` with the pre-import snapshot and the new asset hashes. For each genuinely new audio ID, run both passes; repeat `--only` to select several IDs in one invocation:

```sh
python3 scripts/transcribe-listening.py \
  --board-id "$BOARD_ID" \
  --model "$ASR_PRIMARY_MODEL" --model-name large-v3 \
  --vad-model "$ASR_VAD_MODEL" \
  --only NEW_REFERENCE_ID

python3 scripts/transcribe-listening.py \
  --board-id "$BOARD_ID" \
  --model "$ASR_CONTROL_MODEL" --model-name large-v3-turbo \
  --pass-name control-vad --vad-model "$ASR_VAD_MODEL" \
  --only NEW_REFERENCE_ID
```

`--only` expects inventory IDs such as `holst-<audio-stem>`, not object IDs. Without it, the script selects the whole accumulated library and reuses passes only when audio/model hashes and options match. Avoid `--force` unless a specific redo is needed. A deliberately different diagnostic pass may use `--pass-name control --no-vad`. `--library` changes the library directory; `--board-id` selects the imported board. The standard-library transcription driver needs no MLX/Qwen environment.

Primary/control parameters are Greek transcription (`el`), beam/best-of 5, initial temperature 0 with normal fallback, no carried text context; VAD options and exact model/source hashes are recorded per pass. They provide repeatability, not guaranteed linguistic correctness.

## Review before generation readiness

Compare primary/control text, timing, omitted/repeated speech warnings and relevant printed lesson material. Resolve substantive differences using the original audio or source page; retain uncertainty explicitly. Do not claim an auditory/native-speaker check when only ASR and printed sources were compared.

Keep raw ASR files unchanged. Write corrections to `reviews/<ID>.json`:

```json
{
  "status": "source_checked",
  "title": "A descriptive lesson title",
  "content_type": "dialogue",
  "text": "Reviewed Greek source text",
  "notes": ["Describe the actual checks and any limits."],
  "audio_sha256": "COPY_THE_ACTUAL_AUDIO_SHA256",
  "primary_json_sha256": "COPY_THE_ACTUAL_PRIMARY_JSON_SHA256",
  "source_images": ["data/boards/<board-id>/assets/files/example.png"],
  "reference_ready": true
}
```

Review statuses: `automatic_transcript`, `text_reviewed`, `source_checked`, `needs_audio_check`. The first three do not imply a full human listening check. Classify the actual content (dialogue, monologue, phonetics or another useful type). Set `reference_ready: true` only after resolving material uncertainties; keep dubious records out of generation-ready references. Role labels must follow source evidence, not blind line alternation.

whisper.cpp may emit invalid UTF-8 in individual token byte fragments while the complete segment text remains valid. The driver preserves `.json.original-bytes` and normalizes only that technical token output. Invalid bytes in actual segment text are an error; do not replace the segment's words to make processing pass.

After review:

```sh
python3 scripts/transcribe-listening.py --board-id "$BOARD_ID" --publish-only
```

The command rebuilds:

| File/directory | Purpose |
| --- | --- |
| `inventory.json` | Accumulated source hashes and all board occurrences. |
| `raw/primary`, `raw/control-vad`, `raw/control` | Original TXT/SRT/JSON, run options and logs. |
| `reviews/` | Corrections and precise review claims, hash-bound to audio/ASR. |
| `transcripts/*.txt`, `transcripts/*.md` | Reviewed text, original audio link and provenance. |
| `manifest.json` | Checks, review metadata and paths. |
| `index.md`, `context.md`, `corpus.jsonl` | Catalog, combined learning context and machine-readable records. |
| `generation-references.jsonl` | Only records explicitly marked ready for generation. |

Verify old records remain, new sources are cataloged, links/hashes resolve and readiness matches the review. If source/ASR bytes change, a stale review hash must be rechecked. Token confidence and model agreement do not prove correctness or learner mastery.

For new material inspired by these recordings, use [greek-listening-practice](../../greek-listening-practice/SKILL.md). It writes separate generated files under `data/listening-generated/practice/`; source transcripts remain intact.
