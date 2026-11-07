# Evidence schema

`analysis/evidence.jsonl` contains one JSON object per line:

```json
{
  "skillId": "grammar.noun_gender",
  "label": "Род существительных: ο / η / το",
  "category": "grammar",
  "status": "practiced",
  "confidence": 0.82,
  "source": {
    "objectId": "holst-object-id",
    "assetPath": "assets/files/example.webp",
    "frameId": "optional-frame-id"
  },
  "evidenceType": "completed_exercise",
  "observation": "Заполнено упражнение на выбор ο, η или το"
}
```

Allowed categories:

- `grammar`
- `vocabulary`
- `conversation_topic`
- `language_function`
- `pronunciation`

Allowed statuses:

- `introduced`: material appears on the board.
- `practiced`: there is evidence of an attempted or completed exercise.
- `needs_review`: errors, corrections, or uncertainty are visible.
- `confirmed`: supported by a separate diagnostic or conversation assessment, never by board presence alone.
- `no_evidence`: an explicit curriculum item was checked but no supporting material was found.

Every entry must include a concrete observation and at least one source reference. Do not infer mastery from a textbook page alone.
