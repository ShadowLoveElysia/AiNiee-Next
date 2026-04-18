"""
AiNiee MCP server package.

This package is intentionally optional. Core runtime must not import it
unconditionally.
"""

from .runtime import inspect_mcp_runtime

__all__ = ["inspect_mcp_runtime"]
