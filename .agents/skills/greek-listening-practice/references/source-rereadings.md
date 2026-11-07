# Explicit source rereadings

Use this mode only when the user asks to re-record an existing lesson, rather than create a new situation. Read its reviewed reference transcript and available role labels from source images/audio. Preserve the words; headings and exercise numbers are unspoken metadata.

Prepare an explicit role-based `script.json` compatible with `scripts/synthesize-role-dialogues.py`: each role has a fixed `male-greek` or `female-greek` voice, and each ordered turn identifies its actual speaker and Greek text. Do not infer speakers solely from sentence/line boundaries. Mark uncertain role assignments. Source scenes with more than two speakers require an explicit plan rather than silently relabeling them as a newly generated two-person dialogue.

Store derivative work in private `data/listening-generated/role-dialogues/<descriptive-name>/`. Keep source transcripts unchanged. The script fields are:

| Field | Meaning |
| --- | --- |
| `artifact_type` | `generated_role_reading`; never `generated_practice` for a source rereading. |
| `format`, `file_stem`, `title` | `dialogue` or `monologue`, descriptive English format/topic stem, and unspoken title. |
| `source_transcript`, `source_sha256` | Project-relative reviewed source TXT path and its actual SHA-256. |
| `source_reference_id` | The original library reference ID. |
| `roles`, `turns` | The same fixed voice mapping and ordered role/text structure as [new practice](workflow.md#prepare-and-author). |
| `casting_note`, `role_assignment_status` | Explain source evidence for speakers and any uncertainties. |
| `omitted_headings` | Optional array of exact source headings to omit from speech. |

The renderer verifies the transcript hash and exact spoken text after removing only the declared headings and normalizing whitespace. This source-preservation mode does not pass through the new-practice novelty validator.

```sh
python3 scripts/synthesize-role-dialogues.py \
  data/listening-generated/role-dialogues/my-rereading/script.json \
  --check-asr --asr-model /path/to/ggml-large-v3.bin
```

The [runtime requirements and configuration](workflow.md#runtime-prerequisites) are the same as new practice. Check source text conservation, role consistency, actual framing of pauses and the ASR comparison. Deliver the complete transcript directly below the recording and call it a source rereading. Old experimental Qwen/system-voice comparisons and deliberately slowed presets are historical utilities, not the default Greek workflow.
