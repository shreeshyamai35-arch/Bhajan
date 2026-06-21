# SKILL: mix_and_master  (Mixing Agent — audio-mcp; optional LANDR)

Combine the cloned vocal with the instrumental and deliver a professional master.

## Inputs
`runs/{id}/voice/my_voice.wav`, `runs/{id}/stems/instrumental.wav`,
`learning.yaml.mix_preferences`.

## Procedure

1. **Align.**
   - `audio.align({ vocal_path, instrumental_path, dest_path:"...aligned_vocal.wav" })`.
   - Correct any latency offset introduced by conversion.

2. **Vocal chain.**
   - `audio.vocal_chain({ vocal_path: aligned_vocal,
       low_cut_hz:100, presence_db:3.0, comp_ratio:3.0, deess:true,
       reverb_preset: mix_preferences.reverb_preset,
       reverb_predelay_ms: mix_preferences.reverb_predelay_ms })`.
   - Order: cleanup/de-reverb → low cut → presence EQ → compression → de-ess →
     reverb send. Keep it natural and devotional (not over-processed).

3. **Mix.**
   - `audio.mix({ vocal_path: processed_vocal, instrumental_path,
       vocal_gain_db: 0.0, dest_path:"runs/{id}/mix/premaster.wav" })`.
   - Target a vocal-forward but blended balance (target balance ~ +2 dB vocal).

4. **Master.**
   - `audio.master({ input_path:"runs/{id}/mix/premaster.wav",
       dest_path:"runs/{id}/master.wav",
       target_lufs: -14.0, true_peak_dbtp: -1.0,
       reference_track: mix_preferences.master_reference_track,
       use_landr: (LANDR_API_KEY set) })`.
   - matchering matches a reference master if provided; otherwise loudness-normalize
     + true-peak limit to targets. If `use_landr`, send to LANDR at configured
     intensity and download.

5. **Verify targets.**
   - Confirm returned `lufs` within ±1.0 of -14 and `true_peak <= -1.0`. If off,
     re-run master with adjusted gain (do not exceed peak ceiling).

## Output `MixResult`
`premaster_path`, `master_path`, `offset_ms`, `lufs`, `true_peak_dbtp`, `used_landr`.

## Guardrails
- Loudness/peak per rules R3.2/R3.3. No clipping (R3.7).

## Output artifacts
`runs/{id}/mix/premaster.wav`, `runs/{id}/master.wav`.
