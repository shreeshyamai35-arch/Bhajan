# Skill: Produce a Bhajan (end-to-end runbook)

The orchestrator runs the stages below in order, enforcing `config/rules.md` and
reading/writing `config/learning.yaml`. Artifacts land in `runs/{run_id}/`.

## Pipeline
1. **Intake** — validate the request against the rules (devotional only R1.1;
   never clone a third-party voice R2.1). On violation: halt the run.
2. **Lyricist** (`§Lyricist`) — RAG-retrieve context, then write structured
   lyrics (`mukhda` + `antara×N` + optional `aarti_outro`) with pronunciation
   hints; self-validate devotional terms against the KB.
3. **Composer** — `skills/generate_music.md`.
4. **Voice** — `skills/clone_voice.md`.
5. **Mixing** — `skills/mix_and_master.md`.
6. **Quality Judge** — `skills/quality_review.md`. If score < gate, loop back to
   the failing stage (max attempts per `rules.md §4`).
7. **Packager** — `skills/publish.md` (saves locally, no upload).
8. **Memory** — append a `quality_history` entry and update `best_settings`;
   write `runs/{run_id}/manifest.json`.

## §Lyricist
- If `lyrics_override` is set, normalize and skip generation.
- Retrieve top-k: past lyrics (style), scripture (facts), taal/raag, pronunciation.
- Mirror the artist's vocabulary. Never invent scripture — if the KB lacks
  context, flag low confidence and use clearly-traditional phrasing.

## Resuming
`bhajanforge status --run-id ID` shows progress. Re-running `produce` with the
same `--run-id` resumes; completed stages whose artifacts already exist are skipped.
