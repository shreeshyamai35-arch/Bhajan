"""audio-mcp server entrypoint.

The mcp package is imported lazily inside the ``__main__`` guard so that
importing ``core`` (for tests / agents) never requires mcp to be installed.
"""

from __future__ import annotations

if __name__ == "__main__":
    from typing import Optional

    from mcp.server.fastmcp import FastMCP

    from . import core

    mcp = FastMCP("audio")

    @mcp.tool()
    def audio_align(vocal_path: str, instrumental_path: str, dest_path: str) -> dict:
        return core.audio_align(vocal_path, instrumental_path, dest_path)

    @mcp.tool()
    def audio_vocal_chain(
        vocal_path: str,
        dest_path: str,
        low_cut_hz: float = 100.0,
        presence_db: float = 3.0,
        comp_ratio: float = 3.0,
        deess: bool = True,
        reverb_preset: str = "temple_hall",
        reverb_predelay_ms: float = 30.0,
    ) -> dict:
        return core.audio_vocal_chain(
            vocal_path,
            dest_path,
            low_cut_hz=low_cut_hz,
            presence_db=presence_db,
            comp_ratio=comp_ratio,
            deess=deess,
            reverb_preset=reverb_preset,
            reverb_predelay_ms=reverb_predelay_ms,
        )

    @mcp.tool()
    def audio_mix(
        vocal_path: str,
        instrumental_path: str,
        dest_path: str,
        vocal_gain_db: float = 0.0,
    ) -> dict:
        return core.audio_mix(
            vocal_path, instrumental_path, vocal_gain_db=vocal_gain_db, dest_path=dest_path
        )

    @mcp.tool()
    def audio_master(
        input_path: str,
        dest_path: str,
        target_lufs: float = -14.0,
        true_peak_dbtp: float = -1.0,
        provider: Optional[str] = None,
        intensity: str = "medium",
        reference_track: Optional[str] = None,
    ) -> dict:
        return core.audio_master(
            input_path,
            dest_path,
            target_lufs=target_lufs,
            true_peak_dbtp=true_peak_dbtp,
            provider=provider,
            intensity=intensity,
            reference_track=reference_track,
        )

    @mcp.tool()
    def audio_analyze(
        input_path: str,
        reference_voice_embedding: Optional[str] = None,
        vocal_only_path: Optional[str] = None,
    ) -> dict:
        return core.audio_analyze(
            input_path,
            reference_voice_embedding=reference_voice_embedding,
            vocal_only_path=vocal_only_path,
        )

    @mcp.tool()
    def audio_transcribe(input_path: str, language: str = "hi") -> dict:
        return core.audio_transcribe(input_path, language=language)

    mcp.run()
