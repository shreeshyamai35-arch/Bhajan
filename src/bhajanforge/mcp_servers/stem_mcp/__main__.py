"""stem-mcp server entrypoint.

The mcp package is imported lazily inside the ``__main__`` guard so importing
``core`` never requires mcp to be installed.
"""

from __future__ import annotations

if __name__ == "__main__":
    from mcp.server.fastmcp import FastMCP

    from . import core

    mcp = FastMCP("stem")

    @mcp.tool()
    def stem_isolate(input_path: str, dest_dir: str, target: str = "both") -> dict:
        return core.stem_isolate(input_path, dest_dir, target=target)

    @mcp.tool()
    def stem_batch_isolate(input_dir: str, dest_dir: str, target: str = "vocals") -> dict:
        return core.stem_batch_isolate(input_dir, dest_dir, target=target)

    mcp.run()
