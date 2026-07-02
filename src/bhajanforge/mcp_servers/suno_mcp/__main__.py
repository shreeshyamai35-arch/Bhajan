"""Entry point for the suno-mcp server.

Run with: ``python -m bhajanforge.mcp_servers.suno_mcp``

The mcp package is imported lazily inside ``__main__`` so importing ``core``
never requires the mcp dependency (tests call ``core`` in-process).
"""

from __future__ import annotations

if __name__ == "__main__":
    from mcp.server.fastmcp import FastMCP

    from .core import (
        suno_download,
        suno_extract_stems,
        suno_generate,
        suno_get_task,
        suno_health,
    )

    mcp = FastMCP("suno-mcp")

    mcp.tool(name="suno.generate")(suno_generate)
    mcp.tool(name="suno.get_task")(suno_get_task)
    mcp.tool(name="suno.download")(suno_download)
    mcp.tool(name="suno.extract_stems")(suno_extract_stems)
    mcp.tool(name="suno.health")(suno_health)

    mcp.run()
