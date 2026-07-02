"""MCP servers for BhajanForge (suno, rvc, stem, audio).

Each server is a thin wrapper around a cloud (or CPU) provider, exposed via the
Model Context Protocol. Every tool returns the common envelope from
``common.ok`` / ``common.err``. No local GPU is required.
"""
