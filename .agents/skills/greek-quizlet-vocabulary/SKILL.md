---
name: greek-quizlet-vocabulary
description: Add Greek–Russian words and phrases from user-supplied Quizlet sets to Greek Context's private dictionary, retaining every source card, reviewed corrections and exact-pair deduplication. Use for new Quizlet links or vocabulary imports, not for general translation or Holst board sync.
---

# Greek Quizlet Vocabulary

Work from the repository root, read `AGENTS.md` and use `scripts/import-quizlet.py`. The helper merges local captures; it does not access Quizlet. Keep the dictionary, snapshots, reviews and reports under ignored `data/vocabulary/`.

1. Read [capture and review format](references/capture-format.md). Open the exact supplied sets with the authorized official Chrome DevTools tools, following the active environment's background-tab/profile instructions. Reuse the dedicated connection. A personal-profile tab requires the user's explicit request for that exact existing tab; do not inspect credentials or change sessions. If human verification appears, ask the user to complete it and continue independent sets. Do not automate or bypass CAPTCHA.
2. Read all rendered cards and the displayed total. Expand/load remaining cards through the normal UI when needed. Save the literal Greek/Russian text, card order, title, URL, extraction time and exact displayed/extracted counts to `data/vocabulary/quizlet/raw/<set-id>.json`. Mark a capture complete only when every card is present. Do not infer missing terms from another set or search snippets.
3. Review spelling, accents and translations. Keep articles, gender pairs and phrases intact. Preserve source text in the raw capture; supply any justified edits in a separate corrections JSON with original, corrected text and a reason/source. Do not silently correct or claim the learner mastered the set.
4. Preview the complete merge:

   ```sh
   python3 scripts/import-quizlet.py \
     data/vocabulary/quizlet/raw/SET_ID.json --dry-run
   ```

   Add `--corrections data/vocabulary/quizlet/reviews/import.json` when there are reviewed edits. Inspect new-entry counts and source coverage, then run the same command without `--dry-run`.
5. Validate the whole dictionary:

   ```sh
   python3 scripts/import-quizlet.py --validate-only
   ```

   Every captured row must appear exactly once in provenance, with reconstructable original Greek/Russian text. Deduplicate only exact NFC/outer-trim pairs, preserving case, articles, synonyms and gender alternatives. Preserve existing entry metadata and corrections. Repeat imports are no-ops; a changed previously imported set requires explicit revision review rather than automatic replacement.
6. Report cards imported, genuinely new dictionary entries, final totals and any unresolved source issues. Link the local dictionary if useful. Presence in Quizlet establishes introduced source vocabulary, not `practiced` or `confirmed` proficiency.

The helper validates before writing, backs up an existing dictionary under `quizlet/history/`, updates `quizlet/sources.json` and `quizlet/validation.json`, and leaves raw captures intact. `--dry-run` and `--validate-only` write nothing. Multiple snapshot paths can be imported together; `--dictionary` selects another private dictionary location.
