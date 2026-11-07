# Quizlet capture, corrections and invariants

The canonical capture is UTF-8 JSON. Store it beneath the dictionary directory, normally `data/vocabulary/quizlet/raw/<set-id>.json`. It represents rendered site content, not an API request or a model's reconstruction.

```json
{
  "id": "123456789",
  "title": "The actual Quizlet set title",
  "url": "https://quizlet.com/123456789/",
  "extracted_at": "2026-01-01T12:00:00Z",
  "card_count": 2,
  "extracted_card_count": 2,
  "complete": true,
  "extraction_method": "Rendered cards through authorized Chrome DevTools",
  "cards": [
    {"row": 1, "greek": "ο καφές", "russian": "кофе"},
    {"row": 2, "greek": "το νερό", "russian": "вода"}
  ]
}
```

Use the actual displayed set count for `card_count` and the captured row count for `extracted_card_count`. Rows must be contiguous 1..N, with one nonempty Greek/Russian pair each. Both counts, the number of rows and `complete: true` must agree. The numeric ID must match the Quizlet URL. A partial snapshot may be retained locally for progress, but cannot be imported as complete.

Historical snapshots with `set_id` and `rows:[{source_row,sides:[{language:"el",text:…},{language:"ru",text:…}]}]` are supported when validating existing dictionary sources with their original verified counts. New captures should use the canonical format above.

## Explicit editorial corrections

Use a separate JSON array, one edit per set/row/field:

```json
[
  {
    "set_id": "123456789",
    "row": 1,
    "field": "greek",
    "original": "ο καφες",
    "corrected": "ο καφές",
    "reason": "Restored the missing stress after checking the source.",
    "reference_url": "https://example.org/the-actual-supporting-source"
  }
]
```

This example edit applies only if the actual captured row has `ο καφες`; the earlier capture example already has the accent. `field` is `greek` or `russian`. Use actual supporting sources or board asset references where appropriate; never invent a reference. An obvious typo still needs an explicit reason. The helper records source-scoped originals and edits on the entry while leaving the capture literal. Corrections apply to newly imported sets; changing an older entry is a separate deliberate revision.

## Dictionary invariants

The existing schema is `schema_version: 1` with `sources`, `entries` and `summary`. Entries have Greek/Russian text and `sources:[{set_id,row}]`; optional metadata, `corrections`, numeric translations and editorial notes must survive later imports.

- The pair key is NFC plus outer whitespace trimming. Do not lowercase, strip articles/accents, split alternatives, or merge translations with different wording.
- Multiple identical cards share an entry, with every source row retained once.
- A correction may produce an existing canonical pair; keep both provenance and the scoped correction.
- Raw text must be reconstructable via correction originals and historical `source_translation` fields.
- Existing set content is immutable during an add-new-sets operation. A changed set is rejected so its revision can be reviewed without erasing old provenance.
- A new source gets `evidence_level: introduced` and `mastery_assessed: false`. Do not carry a previous source's teacher-study or proficiency claim into a newly supplied set.

The CLI accepts Python's standard library only. It creates a new dictionary if none exists, validates all available snapshots before a write, and makes a timestamped backup before changing an existing dictionary. On a malformed/incomplete input, fix the capture or report the specific blocker; do not weaken validation to obtain an import count.
