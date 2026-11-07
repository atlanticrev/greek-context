---
name: greek-holst-context-sync
description: Update the Greek Context learner profile from the latest authorized Holst board, review only new or changed material, and transcribe new source audio into the listening-reference library. Use for board/context sync or adding newly taught material, not for generating practice audio.
---

# Greek Holst Context Sync

Work from this repository's root and read `AGENTS.md`. The normalized board, evidence, profiles, source assets and reviewed audio library form the versioned shared learning base. Pull current changes before a sync, preserve existing evidence, and commit the resulting canonical data together. Raw backups and temporary work remain local; account sessions and credentials must never enter the repository.

1. Read [the sync procedure](references/board-sync.md). Resolve the board from shared `data/local-board.json` or a supplied board URL. Preserve the previous evidence, catalog, profile and audio inventory before importing.
2. Use the authorized existing Chrome connection and the official Google Chrome DevTools tools. Follow the active environment's background-tab/profile instructions; on a configured machine also read `$HOME/.codex/docs/google-chrome-workflow.md` if present. Reuse sessions, preserve focus and keep task tabs in an owned background group. A personal-profile tab requires the user's explicit request for that exact existing tab. Do not inspect cookies/tokens, replace profiles or bypass sign-in/CAPTCHA. If login or human verification blocks access, request that input while continuing independent work.
3. Export the latest board through its rendered UI and wait for a completed, fresh `.holst` download. Import that file with `import-latest`, using the actual download directory. Do not mistake an old backup for a fresh sync.
4. Inspect every queued new/changed text and educational asset, including audio. Reused content needs no second review. Record a disposition for decorative/unrelated material; compare removed/changed source references against existing evidence. Use [the evidence schema](references/evidence-schema.md): source presence is `introduced`, completed attempts may support `practiced`, and board presence never establishes `confirmed`.
5. For new audio, follow [the source-audio library procedure](references/listening-library.md): local primary/control transcription, explicit review and source links, then rebuild the catalog and generation-ready references. Preserve raw ASR and original audio; do not generate substitute recordings.
6. Merge reviewed evidence without losing existing observations. Only after all queued items have a recorded disposition, run `build-profile`: it also advances the analyzed checkpoint. Verify source integrity, output counts and the remaining queue. Keep unresolved items pending instead of marking them analyzed.
7. Deliver the updated local context/profile links, a concise account of new material and any unresolved limitations. If a ChatGPT baseline exists, include the cumulative `chat-context-update.md`; do not reset that baseline unless the user intentionally replaces the full uploaded profile.

If the user also asks for new dialogues or monologues, continue with [greek-listening-practice](../greek-listening-practice/SKILL.md). It consumes this profile, the dictionary and reviewed audio references; syncing alone does not authorize synthesis.
