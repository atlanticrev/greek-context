# Codex analysis prompt

Use this prompt from the `greek-context` project after `import` or `sync`:

```text
Read data/boards/<board-id>/analysis/queue.json and docs/evidence-schema.md.

Inspect every new or changed text item in `textItems` and every educational image
referenced by `assetItems`.
Do not reopen content listed in `reusedTextItems` or `reusedAssetItems`; those are
reference-only records for identical content that was already analyzed.
Ignore avatars, UI graphics, decorative media, and unrelated personal photos.

Extract evidence about:
- grammar;
- vocabulary domains;
- conversation topics;
- language functions;
- pronunciation when explicitly present;
- completed exercises, errors, and teacher corrections.

Write one valid JSON object per line to
data/boards/<board-id>/analysis/evidence.jsonl.

Do not mark anything confirmed from the board alone. Every inference must cite
an objectId, frameId, or assetPath and contain a concrete observation.

After validation, run:
npm run dev -- build-profile <board-id>

`build-profile` also records the current catalog as analyzed. The next sync will
therefore queue only new or changed content, using text hashes and asset SHA-256
digests rather than filenames. If a ChatGPT baseline has been initialized, it
also regenerates `output/chat-context-update.md` as the cumulative diff to upload
instead of replacing the full Project sources.
```
