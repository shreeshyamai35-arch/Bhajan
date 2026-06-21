# SKILL: clone_voice  (Voice Agent — RVC; optional ACE)

Two modes: **Training** (one-time setup) and **Conversion** (per bhajan).

---

## A) TRAINING  (one-time / when retraining)  — FR-23

Goal: build an RVC model of the artist's voice from their existing recordings.

1. **Collect sources.**
   - `knowledge_base/sources/youtube_urls.txt` lists the artist's bhajan URLs.
   - Download audio with `yt-dlp` → `downloads/`.

2. **Isolate clean vocals (cloud).**
   - `stem.batch_isolate({ input_dir:"downloads/", dest_dir:"models/datasets/shyam/",
     target:"vocals" })` (LALAL.AI / Replicate Demucs / free Colab-Kaggle tunnel).
   - Manually/auto-trim silence & noisy regions. Aim for **30–60+ min** of clean
     singing (more is better up to a point).

3. **Train (cloud — no local GPU).**
   - Zip the dataset, then `rvc.train({ dataset_url_or_zip:"models/datasets/shyam.zip",
     model_name:"shyam_voice_v1", sample_rate:48000, version:"v2", epochs:200,
     f0_method:"rmvpe_gpu", batch_size:7 })` → poll `rvc.get_train_task`.
   - Backend per `VOICE_PROVIDER`: Replicate (paid, reliable) or a free
     Colab/Kaggle tunnel (`notebooks/README.md`).

4. **Detect range + register in learning.yaml.**
   - `rvc.detect_range({ vocals_dir:"models/datasets/shyam/" })` →
     write `voice_profile.range`.
   - Set `voice_profile.active_rvc_model` (model reference),
     `active_rvc_provider`, `reference_embedding` (speaker embedding from clean
     vocals for similarity checks), and initial `best_settings`.

DoD (AC-6): cloud model trained + registered; range auto-detected; a test
conversion sounds like the artist.

---

## B) CONVERSION  (per bhajan)  — FR-10..FR-13

Input: `stems/guide_vocal.wav` from the Composer.

1. **Clean the guide vocal (only if needed).**
   - If Suno stems are already clean, skip. Otherwise
     `stem.isolate({ input_path:"runs/{id}/stems/guide_vocal.wav",
     dest_dir:"runs/{id}/stems", target:"vocals" })` → `cleaned_vocal.wav`.

2. **Pick pitch shift.**
   - Keep melody within `voice_profile.range`. Compute needed semitone shift; if
     the guide is far out of range, shift by octave-safe steps (R5.2).

3. **Convert with best settings.**
   - `rvc.convert({ input_path:"cleaned_vocal.wav",
     model_name: voice_profile.active_rvc_model,
     pitch_shift_semitones, index_ratio, f0_method, protect_voiceless,
     resample_sr, dest_path:"runs/{id}/voice/my_voice.wav" })`.

4. **Self-check similarity.**
   - Compute cosine similarity vs `reference_embedding`
     (`audio.analyze` with embedding). If `< voice_similarity_min` (0.95):
     retry with adjusted `index_ratio` (e.g. +0.05) and/or alternate `f0_method`
     before accepting (R5.3). Avoid settings flagged bad in learning history.

5. **Output `VoiceResult`** (path + settings_used + similarity).

## Optional ACE Studio path (SVS)
If `ACE_ENABLED=true` and a guide vocal is undesirable:
`browser.ace_synthesize({ midi, lyrics, voice })` to synthesize directly from
notes in the artist's ACE custom voice; export to `runs/{id}/voice/my_voice.wav`.

## Guardrails
- ONLY the artist's voice (R2.1/R2.2). Defensive hard-stop if asked otherwise.

## Output artifacts
`runs/{id}/stems/cleaned_vocal.wav`, `runs/{id}/voice/my_voice.wav`.
