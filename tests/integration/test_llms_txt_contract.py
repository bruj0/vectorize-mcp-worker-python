"""Contract tests: verify src/llms_txt.py stays in sync with metadata.

Three layers of verification:
  6d. Freshness -- generated content matches render_llms_txt()
  6e. Content completeness -- every operation, endpoint, parameter is present
  6f. Generator round-trip -- running the script produces identical output
"""

from __future__ import annotations

import importlib
import sys
import tempfile
from pathlib import Path

import pytest

# Ensure project paths are importable
_project_root = Path(__file__).parent.parent.parent
_src_dir = str(_project_root / "src")
_stubs_dir = str(_project_root / "tests" / "stubs")
_mcp_tool_src = str(_project_root / "vectorize-mcp-tool" / "src")
_scripts_dir = str(_project_root / "scripts")

for p in (_stubs_dir, _src_dir, _mcp_tool_src, _scripts_dir):
    if p not in sys.path:
        sys.path.insert(0, p)


# ── 6d: Freshness check ─────────────────────────────────────────────────────

class TestLlmsTxtFreshness:
    """The committed src/llms_txt.py must match render_llms_txt() output."""

    def test_generated_content_matches_metadata(self) -> None:
        from vectorize_mcp_tool.metadata import render_llms_txt
        from llms_txt import get_llms_txt

        expected = render_llms_txt()
        actual = get_llms_txt()

        assert actual == expected, (
            "src/llms_txt.py is stale -- run "
            "'cd vectorize-mcp-tool && uv run python ../scripts/generate_llms_txt.py' "
            "to regenerate"
        )


# ── 6e: Content completeness ────────────────────────────────────────────────

class TestLlmsTxtContent:
    """Every operation, endpoint, and parameter from metadata must appear."""

    def test_all_operations_present(self) -> None:
        from vectorize_mcp_tool.metadata import OPERATION_NAMES
        from llms_txt import get_llms_txt

        content = get_llms_txt()
        missing = [op for op in OPERATION_NAMES if op not in content]
        assert not missing, f"Operations missing from llms.txt: {missing}"

    def test_all_endpoint_paths_present(self) -> None:
        from vectorize_mcp_tool.metadata import ENDPOINTS
        from llms_txt import get_llms_txt

        content = get_llms_txt()
        missing = [ep["path"] for ep in ENDPOINTS if ep["path"] not in content]
        assert not missing, f"Endpoint paths missing from llms.txt: {missing}"

    def test_all_parameter_names_present(self) -> None:
        from vectorize_mcp_tool.metadata import PARAMETERS
        from llms_txt import get_llms_txt

        content = get_llms_txt()
        missing = [name for name in PARAMETERS if name not in content]
        assert not missing, f"Parameters missing from llms.txt: {missing}"

    def test_mcp_endpoints_not_present(self) -> None:
        """The old /mcp/tools and /mcp/call endpoints must NOT appear."""
        from llms_txt import get_llms_txt

        content = get_llms_txt()
        assert "/mcp/tools" not in content, "/mcp/tools should not appear in llms.txt"
        assert "/mcp/call" not in content, "/mcp/call should not appear in llms.txt"

    def test_mentions_mcp_tool_package(self) -> None:
        from llms_txt import get_llms_txt

        content = get_llms_txt()
        assert "vectorize-mcp-tool" in content


# ── 6f: Generator round-trip ─────────────────────────────────────────────────

class TestGeneratorRoundTrip:
    """Running the generator script must produce identical output."""

    def test_generator_produces_same_output(self) -> None:
        # Import the generator script
        generate_mod_path = _project_root / "scripts" / "generate_llms_txt.py"
        assert generate_mod_path.exists(), f"Generator script not found: {generate_mod_path}"

        spec = importlib.util.spec_from_file_location("generate_llms_txt", generate_mod_path)
        gen_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(gen_mod)

        # Generate to a temp directory
        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = gen_mod.generate(Path(tmpdir))
            generated = out_path.read_text(encoding="utf-8")

        # Compare to committed file
        committed = (_project_root / "src" / "llms_txt.py").read_text(encoding="utf-8")

        assert generated == committed, (
            "Generator script produces different output than committed src/llms_txt.py. "
            "Run 'cd vectorize-mcp-tool && uv run python ../scripts/generate_llms_txt.py' "
            "to regenerate."
        )
