"""Entry point for the rvc-mcp server.

Run with: ``python -m bhajanforge.mcp_servers.rvc_mcp``

The mcp package is imported lazily inside ``__main__`` so importing ``core``
never requires the mcp dependency (tests call ``core`` in-process).
"""

from __future__ import annotations

if __name__ == "__main__":
    from mcp.server.fastmcp import FastMCP

    from .core import (
        rvc_convert,
        rvc_detect_range,
        rvc_get_train_task,
        rvc_list_models,
        rvc_train,
    )

    mcp = FastMCP("rvc-mcp")

    mcp.tool(name="rvc.list_models")(rvc_list_models)
    mcp.tool(name="rvc.convert")(rvc_convert)
    mcp.tool(name="rvc.train")(rvc_train)
    mcp.tool(name="rvc.get_train_task")(rvc_get_train_task)
    mcp.tool(name="rvc.detect_range")(rvc_detect_range)

    mcp.run()
