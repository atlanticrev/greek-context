# Learning evidence

`data/boards/<board-id>/analysis/evidence.jsonl` contains one object per line:

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

Categories: `grammar`, `vocabulary`, `conversation_topic`, `language_function`, `pronunciation`.

| Status | Supported inference |
| --- | --- |
| `introduced` | Material appears in a lesson, reference or teaching example. |
| `practiced` | Evidence of a learner attempt or completed exercise. |
| `needs_review` | Visible errors, corrections or specific uncertainty. |
| `confirmed` | Separate diagnostic or conversation assessment; never board presence alone. |
| `no_evidence` | An explicit curriculum item was checked but supporting material was not found. |

Use a concrete observation, confidence between 0 and 1, and at least one resolvable object, frame or asset reference for every inference. Prefer stable existing skill IDs. Absence of evidence does not establish inability. Audio transcripts and Quizlet sets do not imply mastered vocabulary.
