"""vectorize-mcp-tool -- CLI and MCP server for the Vectorize knowledge base worker."""

__version__ = "0.1.0"

from vectorize_mcp_tool.client import VectorizeClient

__all__ = ["VectorizeClient", "__version__"]
