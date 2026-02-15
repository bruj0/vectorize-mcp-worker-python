"""Click CLI for the Vectorize MCP Worker REST API.

Entry point ``main()`` is registered as ``vectorize-mcp`` in pyproject.toml.

Configuration:
    --url / VECTORIZE_URL         Worker base URL (required)
    --api-key / VECTORIZE_API_KEY Bearer token   (required)
"""

from __future__ import annotations

import asyncio
import json
import sys
from typing import Any

import click

from vectorize_mcp_tool.client import VectorizeClient


# ── Helpers ───────────────────────────────────────────────────────────────────


def _run(coro: Any) -> Any:
    """Run an async coroutine from synchronous Click handlers."""
    return asyncio.run(coro)


def _output(data: dict[str, Any]) -> None:
    """Pretty-print JSON to stdout."""
    click.echo(json.dumps(data, indent=2))


def _error(msg: str, code: int = 1) -> None:
    """Print an error message to stderr and exit."""
    click.echo(f"Error: {msg}", err=True)
    sys.exit(code)


# ── Root group ────────────────────────────────────────────────────────────────


@click.group()
@click.option(
    "--url",
    envvar="VECTORIZE_URL",
    required=True,
    help="Deployed worker base URL.  [env: VECTORIZE_URL]",
)
@click.option(
    "--api-key",
    envvar="VECTORIZE_API_KEY",
    required=True,
    help="Bearer API key.  [env: VECTORIZE_API_KEY]",
)
@click.pass_context
def cli(ctx: click.Context, url: str, api_key: str) -> None:
    """CLI for the Vectorize knowledge base worker."""
    ctx.ensure_object(dict)
    ctx.obj["client"] = VectorizeClient(url, api_key)


# ── search (subgroup) ────────────────────────────────────────────────────────


@cli.group("search")
def search_group() -> None:
    """Search commands."""


@search_group.command("multimodal")
@click.argument("query")
@click.option("--top-k", default=5, show_default=True, help="Number of results (1-20).")
@click.option("--rerank/--no-rerank", default=True, show_default=True, help="Cross-encoder reranking.")
@click.option("--offset", default=0, show_default=True, help="Pagination offset.")
@click.option("--snippet-length", default=200, show_default=True, help="Snippet length (50-500).")
@click.pass_context
def search_multimodal(ctx: click.Context, query: str, top_k: int, rerank: bool, offset: int, snippet_length: int) -> None:
    """Hybrid search returning docs + images (snippet + metadata)."""
    client: VectorizeClient = ctx.obj["client"]
    try:
        result = _run(client.search_multimodal(query, top_k=top_k, rerank=rerank, offset=offset, snippet_length=snippet_length))
        _output(result)
    except Exception as exc:
        _error(str(exc))


@search_group.command("documents")
@click.argument("query")
@click.option("--top-k", default=5, show_default=True, help="Number of results (1-20).")
@click.option("--rerank/--no-rerank", default=True, show_default=True, help="Cross-encoder reranking.")
@click.option("--offset", default=0, show_default=True, help="Pagination offset.")
@click.option("--snippet-length", default=200, show_default=True, help="Snippet length (50-500).")
@click.pass_context
def search_documents(ctx: click.Context, query: str, top_k: int, rerank: bool, offset: int, snippet_length: int) -> None:
    """Hybrid search returning documents only (snippet + metadata)."""
    client: VectorizeClient = ctx.obj["client"]
    try:
        result = _run(client.search_documents(query, top_k=top_k, rerank=rerank, offset=offset, snippet_length=snippet_length))
        _output(result)
    except Exception as exc:
        _error(str(exc))


@search_group.command("similar-images")
@click.option("--file", "file_path", required=True, type=click.Path(exists=True), help="Path to the query image.")
@click.option("--top-k", default=5, show_default=True, help="Number of results.")
@click.pass_context
def search_similar_images(ctx: click.Context, file_path: str, top_k: int) -> None:
    """Find visually similar images (image file input)."""
    client: VectorizeClient = ctx.obj["client"]
    try:
        result = _run(client.find_similar_images(file_path, top_k=top_k))
        _output(result)
    except Exception as exc:
        _error(str(exc))


# ── ingest (subgroup) ────────────────────────────────────────────────────────


@cli.group("ingest")
def ingest_group() -> None:
    """Ingestion commands."""


@ingest_group.command("document")
@click.option("--id", "doc_id", required=True, help="Document ID.")
@click.option("--content", required=True, help="Document text content.")
@click.option("--category", default=None, help="Optional category tag.")
@click.option("--title", default=None, help="Optional document title.")
@click.pass_context
def ingest_document(ctx: click.Context, doc_id: str, content: str, category: str | None, title: str | None) -> None:
    """Ingest a text document with auto-chunking."""
    client: VectorizeClient = ctx.obj["client"]
    try:
        result = _run(client.ingest(doc_id, content, category=category, title=title))
        _output(result)
    except Exception as exc:
        _error(str(exc))


@ingest_group.command("image")
@click.option("--id", "doc_id", required=True, help="Document ID for the image.")
@click.option("--file", "file_path", required=True, type=click.Path(exists=True), help="Path to the image file.")
@click.option("--category", default="images", show_default=True, help="Category tag.")
@click.option("--title", default=None, help="Optional title.")
@click.option(
    "--image-type",
    default="auto",
    show_default=True,
    type=click.Choice(["screenshot", "diagram", "document", "chart", "photo", "auto"]),
    help="Image type hint.",
)
@click.pass_context
def ingest_image(
    ctx: click.Context,
    doc_id: str,
    file_path: str,
    category: str,
    title: str | None,
    image_type: str,
) -> None:
    """Ingest an image via multipart upload."""
    client: VectorizeClient = ctx.obj["client"]
    try:
        result = _run(
            client.ingest_image(doc_id, file_path, category=category, title=title, image_type=image_type)
        )
        _output(result)
    except Exception as exc:
        _error(str(exc))


# ── get (subgroup) ────────────────────────────────────────────────────────────


@cli.group("get")
def get_group() -> None:
    """Retrieve full documents or images by ID."""


@get_group.command("document")
@click.argument("doc_id")
@click.pass_context
def get_document(ctx: click.Context, doc_id: str) -> None:
    """Get full document content by ID."""
    client: VectorizeClient = ctx.obj["client"]
    try:
        result = _run(client.get_document(doc_id))
        _output(result)
    except Exception as exc:
        _error(str(exc))


@get_group.command("image")
@click.argument("img_id")
@click.pass_context
def get_image(ctx: click.Context, img_id: str) -> None:
    """Get full image document by ID."""
    client: VectorizeClient = ctx.obj["client"]
    try:
        result = _run(client.get_image(img_id))
        _output(result)
    except Exception as exc:
        _error(str(exc))


# ── list ──────────────────────────────────────────────────────────────────────


@cli.group("list")
def list_group() -> None:
    """List resources."""


@list_group.command("documents")
@click.option("--limit", default=50, show_default=True, help="Max results (1-200).")
@click.option("--offset", default=0, show_default=True, help="Pagination offset.")
@click.pass_context
def list_documents(ctx: click.Context, limit: int, offset: int) -> None:
    """List documents with pagination."""
    client: VectorizeClient = ctx.obj["client"]
    try:
        result = _run(client.list_documents(limit=limit, offset=offset))
        _output(result)
    except Exception as exc:
        _error(str(exc))


# ── stats ─────────────────────────────────────────────────────────────────────


@cli.command()
@click.pass_context
def stats(ctx: click.Context) -> None:
    """Show index statistics."""
    client: VectorizeClient = ctx.obj["client"]
    try:
        result = _run(client.stats())
        _output(result)
    except Exception as exc:
        _error(str(exc))


# ── delete (subgroup) ─────────────────────────────────────────────────────────


@cli.group("delete")
def delete_group() -> None:
    """Delete resources."""


@delete_group.command("document")
@click.argument("doc_id")
@click.pass_context
def delete_document(ctx: click.Context, doc_id: str) -> None:
    """Delete a document by ID."""
    client: VectorizeClient = ctx.obj["client"]
    try:
        result = _run(client.delete(doc_id))
        _output(result)
    except Exception as exc:
        _error(str(exc))


@delete_group.command("license")
@click.argument("key")
@click.pass_context
def delete_license(ctx: click.Context, key: str) -> None:
    """Delete a license by key."""
    client: VectorizeClient = ctx.obj["client"]
    try:
        result = _run(client.delete_license(key))
        _output(result)
    except Exception as exc:
        _error(str(exc))


# ── health ────────────────────────────────────────────────────────────────────


@cli.command()
@click.pass_context
def health(ctx: click.Context) -> None:
    """Health check (no authentication required)."""
    client: VectorizeClient = ctx.obj["client"]
    try:
        result = _run(client.health())
        _output(result)
    except Exception as exc:
        _error(str(exc))


# ── reset (subgroup) ─────────────────────────────────────────────────────────


@cli.group("reset")
def reset_group() -> None:
    """Database reset commands (require passphrase)."""


@reset_group.command("init-passphrase")
@click.option("--passphrase", prompt=True, hide_input=True, confirmation_prompt=True, help="Reset passphrase (min 8 chars).")
@click.pass_context
def reset_init_passphrase(ctx: click.Context, passphrase: str) -> None:
    """Set or rotate the reset passphrase."""
    client: VectorizeClient = ctx.obj["client"]
    try:
        result = _run(client.init_reset_passphrase(passphrase))
        _output(result)
    except Exception as exc:
        _error(str(exc))


@reset_group.command("all")
@click.option("--passphrase", prompt=True, hide_input=True, help="Reset passphrase.")
@click.pass_context
def reset_all(ctx: click.Context, passphrase: str) -> None:
    """Wipe ALL databases (documents, vectors, licenses). Requires passphrase."""
    client: VectorizeClient = ctx.obj["client"]
    try:
        result = _run(client.reset_all(passphrase))
        _output(result)
    except Exception as exc:
        _error(str(exc))


@reset_group.command("documents")
@click.option("--passphrase", prompt=True, hide_input=True, help="Reset passphrase.")
@click.pass_context
def reset_documents(ctx: click.Context, passphrase: str) -> None:
    """Wipe documents and vectors. Requires passphrase."""
    client: VectorizeClient = ctx.obj["client"]
    try:
        result = _run(client.reset_documents(passphrase))
        _output(result)
    except Exception as exc:
        _error(str(exc))


@reset_group.command("licenses")
@click.option("--passphrase", prompt=True, hide_input=True, help="Reset passphrase.")
@click.pass_context
def reset_licenses(ctx: click.Context, passphrase: str) -> None:
    """Wipe all licenses. Requires passphrase."""
    client: VectorizeClient = ctx.obj["client"]
    try:
        result = _run(client.reset_licenses(passphrase))
        _output(result)
    except Exception as exc:
        _error(str(exc))


# ── license (subgroup) ────────────────────────────────────────────────────────


@cli.group()
def license() -> None:
    """License management commands."""


@license.command("create")
@click.option("--email", required=True, help="Email address for the license.")
@click.option(
    "--plan",
    default="standard",
    show_default=True,
    type=click.Choice(["standard", "pro", "enterprise"]),
    help="Plan tier.",
)
@click.option("--max-documents", default=None, type=int, help="Max documents limit.")
@click.option("--max-queries-per-day", default=None, type=int, help="Max daily queries.")
@click.pass_context
def license_create(
    ctx: click.Context,
    email: str,
    plan: str,
    max_documents: int | None,
    max_queries_per_day: int | None,
) -> None:
    """Create a new license."""
    client: VectorizeClient = ctx.obj["client"]
    try:
        result = _run(
            client.license_create(
                email, plan=plan, max_documents=max_documents, max_queries_per_day=max_queries_per_day
            )
        )
        _output(result)
    except Exception as exc:
        _error(str(exc))


@license.command("validate")
@click.argument("key")
@click.pass_context
def license_validate(ctx: click.Context, key: str) -> None:
    """Validate a license key."""
    client: VectorizeClient = ctx.obj["client"]
    try:
        result = _run(client.license_validate(key))
        _output(result)
    except Exception as exc:
        _error(str(exc))


@license.command("list")
@click.pass_context
def license_list(ctx: click.Context) -> None:
    """List all licenses."""
    client: VectorizeClient = ctx.obj["client"]
    try:
        result = _run(client.license_list())
        _output(result)
    except Exception as exc:
        _error(str(exc))


@license.command("revoke")
@click.argument("key")
@click.pass_context
def license_revoke(ctx: click.Context, key: str) -> None:
    """Revoke a license."""
    client: VectorizeClient = ctx.obj["client"]
    try:
        result = _run(client.license_revoke(key))
        _output(result)
    except Exception as exc:
        _error(str(exc))


# ── serve (starts MCP stdio server) ──────────────────────────────────────────


@cli.command()
@click.pass_context
def serve(ctx: click.Context) -> None:
    """Start the MCP stdio server for Cursor / AI agents.

    Delegates to the FastMCP server defined in vectorize_mcp_tool.server.
    The VECTORIZE_URL and VECTORIZE_API_KEY environment variables are inherited
    from the --url / --api-key options (or their env var equivalents).
    """
    import os

    from vectorize_mcp_tool.server import main as server_main

    # Ensure the env vars are set so the MCP server can pick them up.
    # click already validated these via the root group options.
    client: VectorizeClient = ctx.obj["client"]
    os.environ.setdefault("VECTORIZE_URL", client.base_url)
    os.environ.setdefault("VECTORIZE_API_KEY", client.api_key)

    server_main()


# ── Package entry point ───────────────────────────────────────────────────────


def main() -> None:
    """CLI entry point registered in pyproject.toml."""
    cli()


if __name__ == "__main__":
    main()
