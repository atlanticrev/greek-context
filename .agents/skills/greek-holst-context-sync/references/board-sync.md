# Fresh board import and incremental evidence

Run commands from the repository root. Node.js 20+ and `npm install` are prerequisites. The preferred browser workflow uses an authenticated, authorized Chrome connection and Google's official Chrome DevTools tools; a new user may need to sign in once. Do not run the legacy `auth`/`sync` browser helper when the active environment requires the official tools.

Read board identity from private `data/local-board.json` (format in `examples/local-board.example.json`) or the user's supplied URL. Use that identity consistently. In the examples below, set `BOARD_ID`, `BOARD_NAME` and `DOWNLOAD_DIR` to the user's actual local values; do not put those values in shared documentation.

Before import, preserve the current `analysis/` state, normalized catalog, `output/`, asset manifest and listening-library inventory in a dated private sync-history folder. In particular retain the analyzed checkpoint and the ChatGPT baseline. Do not overwrite evidence or reset a baseline to make a diff disappear.

## Download and import

In the rendered Holst board, choose the export menu and **Download board backup**. Wait for Chrome's completed download state and verify the file's timestamp/name against this export. Some Chrome connections save downloads in the project directory rather than the user's Downloads folder; use the observed location.

```sh
npm run dev -- import-latest \
  --board-id "$BOARD_ID" \
  --name "$BOARD_NAME" \
  --downloads-dir "$DOWNLOAD_DIR" \
  --max-age-minutes 15
```

`--name` filters the filename, so omit it if the actual export uses a different name. An explicitly identified authorized local backup can instead be imported with:

```sh
npm run dev -- import /path/to/board.holst --board-id "$BOARD_ID"
```

No credential extraction or private API token is needed. Do not ask the user to export a file manually when the authorized browser workflow is available.

## Review the delta

Read `data/boards/<board-id>/analysis/queue.json`, `analysis/catalog.json` and `assets/manifest.json`. The queue uses content hashes for text and SHA-256 for assets:

- `textItems` and `assetItems` require review.
- `reusedTextItems` and `reusedAssetItems` are references to already reviewed identical content; do not reopen it.
- Compare previous/current catalogs for removals and changed references. Do not retain a source as current when it has disappeared; preserve historical observations explicitly if useful.

Investigate failed downloads before declaring the import complete. Inspect educational images at readable resolution. Classify audio and use the [audio procedure](listening-library.md). Ignore avatars, UI graphics, decorative media and unrelated personal photographs, but record that disposition so the checkpoint has a reviewable basis.

Write validated JSONL observations to `analysis/evidence.jsonl` using [evidence-schema.md](evidence-schema.md). Preserve existing evidence and stable skill IDs. Add grammar, lexical domains, topics, language functions, explicit pronunciation material, completed exercises, errors and teacher corrections only when the source supports them. Printed answers and teaching templates alone do not establish a learner attempt. Scope new vocabulary separately when an older, narrower skill has a higher evidence level.

Validate JSONL syntax, allowed categories/statuses and confidence, unique observations, and that object/frame/asset references exist in the appropriate snapshot. Check each queued item's disposition and review any contradictions with older evidence.

## Build only after review

```sh
npm run dev -- build-profile "$BOARD_ID"
```

This creates `data/boards/<board-id>/output/{learner-profile.json,chat-context.md,chatgpt-project-instructions.md}` and marks the **entire current catalog** analyzed. It is not a preview command: do not run it early while any new material still needs review.

If `analysis/chatgpt-baseline-profile.json` exists, the command also refreshes `output/chat-context-update.md` as a cumulative diff. Initialize a new baseline only after the user intentionally uploads a fresh full profile:

```sh
npm run dev -- init-chatgpt-baseline "$BOARD_ID"
```

Verify the final skill/status totals and all evidence references. Confirm the checkpoint covers the reviewed catalog; recomputing the queue should yield no pending content only when everything was reviewed. Deliver the current board-specific output paths. Generated context is private by default and is shared with ChatGPT only when the user intends it.
