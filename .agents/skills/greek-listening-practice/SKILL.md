---
name: greek-listening-practice
description: Create newly authored Greek listening dialogues or monologues and local LFM audio from this Greek Context project's studied vocabulary, learner evidence and reviewed source recordings. Use for new listening practice or variants of lessons; source transcription belongs to greek-holst-context-sync.
---

# Greek Listening Practice

Work in this repository and read `AGENTS.md` plus [the workflow and draft schema](references/workflow.md). Create a new text, then synthesize it. Re-record an original lesson only when the user explicitly asks; see [source rereadings](references/source-rereadings.md) for that case.

- A monologue has exactly one speaking role and one Greek LFM voice. A dialogue has exactly two speaking roles, one `male-greek` and one `female-greek`; fix each voice to its role throughout.
- Use the local `lfm3-audio:2b-q8_0` service. Do not silently substitute Qwen, system voices or hosted TTS. Speak at a normal conversational pace, with clear diction and short natural pauses; no slowdown unless explicitly requested.
- Read the latest learner profile, dictionary and reviewed references. Prefer practiced/revision material. Add no new grammar or lexical items by default; documented, editorially checked inflections of attested words are allowed. Source presence does not prove mastery.
- Author a new situation, communicative purpose and facts. Merely changing names in the lesson is insufficient. Preserve original reference transcripts and store generated work under private `data/listening-generated/practice/`.

1. Build a fresh context snapshot with the helper, read its evidence and select appropriate references. If source audio is missing/unreviewed, use [greek-holst-context-sync](../greek-holst-context-sync/SKILL.md) to update the reference library rather than inventing a transcript.
2. Respect the requested format/count. If unspecified, create one short piece of roughly 60–100 words. Write `draft.json` using actual skill, vocabulary and reference IDs. Give the exported files a short English kebab-case `file_stem` including format/topic, such as `dialogue-about-coffee`.
3. Review Greek meaning, agreement, articles/cases, verb forms, accents and punctuation. Record a genuine editorial review and explanations for unattested inflected surfaces. Rewrite truly new vocabulary with studied alternatives.
4. Run `validate`, resolve errors and inspect the closest text matches. Do not weaken novelty checks or fabricate inflection explanations. The script validates sources/forms/similarity; it does not prove grammar or semantic novelty.
5. Run `render` with the configured local service, audio Python and ASR tools. It synthesizes turns separately, preserves their order, assembles MP3/WAV and checks with local Whisper. If a prerequisite is missing, preserve the reviewed text and report the specific blocker; do not change models automatically.
6. Compare ASR with the authored text; investigate omissions, repetition and substantive substitutions, regenerating affected turns if needed. Model agreement or zero WER does not prove pronunciation quality or imply a native-speaker listening check.
7. Deliver audio links and show the complete Greek transcript directly below each, with dialogue role labels. Include matching TXT/Markdown links and explicitly identify the text/audio as newly generated. Keep scripts, turns, provenance and checks alongside the outputs.

Codex authors and reviews the Greek text. The helpers make context preparation, validation and rendering repeatable; they do not autonomously invent the practice or establish learner proficiency.
