# Skill: Mix & Master (Mixing Agent → audio-mcp)

1. **Align** the converted vocal to the instrumental (`audio.align`, offset detect).
2. **Vocal chain** (`audio.vocal_chain`): de-noise/de-reverb cleanup → low cut
   (~100 Hz) → gentle presence EQ → compression → de-ess → reverb
   (`learning.yaml: mix_preferences.reverb_preset`, e.g. `temple_hall`, predelay 30 ms).
3. **Mix** to a premaster (`audio.mix`): vocal-forward but blended.
4. **Master** (`audio.master`) to **-14 LUFS integrated (±1)** and **≤ -1 dBTP**:
   - `MASTERING_PROVIDER=landr` + `LANDR_API_KEY` → LANDR API (primary).
   - else → matchering (if a reference is set) + pyloudnorm normalize + true-peak limit.

**Failure:** loudness/peak off target → re-master with adjusted gain (the quality
loop routes a `mixing` fix back here).
