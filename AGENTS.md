# Greek Context

## Purpose

This repository extracts a Holst board into local, inspectable learning evidence and builds a compact Greek learner profile for ChatGPT.

## Commands

- Install: `npm install`
- Typecheck: `npm run typecheck`
- Test: `npm test`
- Build: `npm run build`
- CLI during development: `npm run dev -- <command>`

## Repository skills

- Board/context updates and new source-audio transcription: `.agents/skills/greek-holst-context-sync/SKILL.md`.
- Greek–Russian Quizlet imports: `.agents/skills/greek-quizlet-vocabulary/SKILL.md`.
- Newly authored listening texts and local audio: `.agents/skills/greek-listening-practice/SKILL.md`.

Keep the workflows, schemas and detailed commands in those skills and their references. Prefer the connected authorized Chrome session plus `import-latest` for Holst; do not ask for a manual export when that workflow is available or inspect browser cookies/tokens.

## Shared learning base

- This project is a shared learning base for its two users. Commit the canonical vocabulary and Quizlet captures, normalized board, evidence and profiles, source images/audio, reviewed transcript library, and generated practice texts with final MP3 files under `data/`.
- Keep account access separate from learning content: never commit browser profiles, cookies, tokens, passwords, `.env` files or other credentials.
- Raw `.holst` archives, sync-history copies, model files, temporary conversions, per-turn audio caches and diagnostic experiments remain local working artifacts. The shared normalized board and source assets preserve the usable learning material without those duplicates.
- Preserve evidence and source links when updating the common base. A shared profile records its source learner's evidence; it does not establish another user's proficiency.

## Learning evidence rules

- Board presence means `introduced`, not mastery.
- Completed exercises may support `practiced`.
- Only a diagnostic or conversation assessment may support `confirmed`.
- Every skill inference must cite one or more source items.
- Use `no_evidence` instead of claiming the learner does not know something.

## Greek audio preferences

- Project default: use local LFM3-Audio for Greek synthesis (`lfm3-audio:2b-q8_0`). Do not select Qwen/Serena, system voices, or another model unless the user explicitly changes this preference. A compatible local service and installed models are prerequisites; the repository does not bundle them.
- Dialogue audio uses two distinct Greek voice presets: `male-greek` and `female-greek`. Assign voices to roles explicitly and keep each role's voice fixed throughout the dialogue; never switch voices by sentence or blindly alternate transcript lines.
- Synthesize spoken turns separately, preserve their order, and join them into one audio per dialogue with natural pauses and consistent loudness. Use clear articulation at a normal conversational pace.
- Store role scripts, separate turns, assembled MP3/WAV and quality checks under `data/listening-generated/`, apart from the source reference library. Share scripts, texts, checks and final MP3 files; intermediate turns and duplicate WAV exports can be regenerated locally.
- When delivering listening audio, show the full Greek transcript directly below each audio link or player in the message, with role labels for dialogues; a TXT/Markdown link alone is not enough. Also keep the matching TXT and Markdown files alongside the audio.

## New listening practice

- For recurring generation requests, use the repository's `.agents/skills/greek-listening-practice/SKILL.md` and `scripts/greek-listening-practice.py`.
- Create genuinely new texts by default. Source lessons are references for the studied topics, grammar and vocabulary, not scripts to re-record. Re-record a source text only when the user explicitly asks for it.
- A newly generated monologue has exactly one speaking role and one LFM Greek voice. A newly generated dialogue has exactly two speaking roles and two distinct LFM Greek voices, permanently assigned. Do not introduce extra characters with speaking turns or share one voice between the two roles.
- Use the current board learner profile, `data/vocabulary/greek-russian.json`, and the reviewed listening-reference library. Prefer practiced material and revision; do not expand grammar or add new lexical items unless the user asks. Ordinary inflected forms of studied words are allowed after editorial review and must be documented when not attested in the source corpus.
- Validate vocabulary, evidence links and novelty before synthesis. Mark both the text and audio as generated; source presence is not evidence of learner mastery. New packs live in `data/listening-generated/practice/`; historical source re-readings remain separate.
- Name user-facing files in short, meaningful English kebab-case, including the format and topic: `dialogue-about-coffee.mp3`, `monologue-about-family.mp3`. Use the same stem for the matching WAV, TXT and Markdown; avoid generic `dialogue.mp3` or `monologue.mp3` for new practice. Set `file_stem` explicitly in each draft.

## Speech tempo and delivery

- User preference: normal conversational speech, with no deliberate slowdown. Do not apply a tempo reduction such as `atempo=0.9` or instruct voices to read slowly unless the user explicitly requests it for that recording. Clear reading means clear diction at a natural pace.
- For Qwen's Ryan, use a steady, natural conversational rhythm and brief natural pauses. Do not request a relaxed, languid or drawn-out delivery. Keep Serena and Ryan as distinct voices when requested.
- Use short natural pauses between turns; do not stretch the recording for listening practice automatically. This overrides the earlier slowed careful-reading preset.
