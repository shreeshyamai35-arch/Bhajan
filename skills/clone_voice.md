# Skill: Clone Voice (Voice Agent → rvc-mcp / stem-mcp)

## Conversion (in-pipeline)
1. `stem.isolate` the guide vocal to remove residual instrumentation (skip if the
   Suno stems are already clean).
2. Keep pitch within the artist's range (`learning.yaml: voice_profile.range`, R5.2).
3. `rvc.convert` with `voice_profile.best_settings` (index_ratio, f0_method,
   protect_voiceless, resample_sr). Output → `voice/my_voice.wav`.
4. Self-check similarity vs the reference embedding. If `< voice_similarity_min`
   (R3.4), retry with an adjusted `index_ratio` / `f0_method` before giving up (R5.3).

## §Training (setup time — FR-23 / AC-6)
`bhajanforge voice train --youtube-urls FILE --model-name NAME`
1. Download the artist's own bhajans (yt-dlp). **Only the artist's recordings (R2.2).**
2. `stem.batch_isolate` → clean vocal dataset.
3. `rvc.train` (cloud; no local GPU) → poll `rvc.get_train_task`.
4. `rvc.detect_range` → auto-detect low/high/median note.
5. Register the model ref + provider + range in `learning.yaml`.

> Backends (identical interface): Replicate (default), free Colab/Kaggle tunnel,
> or Kits. No local GPU is ever required.
