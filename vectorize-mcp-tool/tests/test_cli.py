"""Tests for the Click CLI -- uses CliRunner to verify command structure."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest
from click.testing import CliRunner

from vectorize_mcp_tool.cli import cli


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def base_opts() -> list[str]:
    return ["--url", "https://test.example.com", "--api-key", "test-key"]


class TestCLIStructure:
    def test_help(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "vectorize" in result.output.lower() or "Usage" in result.output

    def test_requires_url(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["health"])
        assert result.exit_code != 0

    def test_health_help(self, runner: CliRunner, base_opts: list[str]) -> None:
        result = runner.invoke(cli, [*base_opts, "health", "--help"])
        assert result.exit_code == 0

    def test_search_group_help(self, runner: CliRunner, base_opts: list[str]) -> None:
        result = runner.invoke(cli, [*base_opts, "search", "--help"])
        assert result.exit_code == 0

    def test_ingest_group_help(self, runner: CliRunner, base_opts: list[str]) -> None:
        result = runner.invoke(cli, [*base_opts, "ingest", "--help"])
        assert result.exit_code == 0

    def test_license_group_help(self, runner: CliRunner, base_opts: list[str]) -> None:
        result = runner.invoke(cli, [*base_opts, "license", "--help"])
        assert result.exit_code == 0

    def test_reset_group_help(self, runner: CliRunner, base_opts: list[str]) -> None:
        result = runner.invoke(cli, [*base_opts, "reset", "--help"])
        assert result.exit_code == 0

    def test_get_group_help(self, runner: CliRunner, base_opts: list[str]) -> None:
        result = runner.invoke(cli, [*base_opts, "get", "--help"])
        assert result.exit_code == 0

    def test_delete_group_help(self, runner: CliRunner, base_opts: list[str]) -> None:
        result = runner.invoke(cli, [*base_opts, "delete", "--help"])
        assert result.exit_code == 0

    def test_stats_help(self, runner: CliRunner, base_opts: list[str]) -> None:
        result = runner.invoke(cli, [*base_opts, "stats", "--help"])
        assert result.exit_code == 0

    def test_list_group_help(self, runner: CliRunner, base_opts: list[str]) -> None:
        result = runner.invoke(cli, [*base_opts, "list", "--help"])
        assert result.exit_code == 0


class TestCLIHealthCommand:
    def test_health_calls_client(self, runner: CliRunner, base_opts: list[str]) -> None:
        with patch(
            "vectorize_mcp_tool.cli.VectorizeClient"
        ) as MockClient:
            instance = MockClient.return_value
            instance.health = AsyncMock(return_value={"status": "healthy"})

            result = runner.invoke(cli, [*base_opts, "health"])

            assert result.exit_code == 0
            assert "healthy" in result.output
            instance.health.assert_called_once()


class TestCLIStatsCommand:
    def test_stats_calls_client(self, runner: CliRunner, base_opts: list[str]) -> None:
        with patch("vectorize_mcp_tool.cli.VectorizeClient") as MockClient:
            instance = MockClient.return_value
            instance.stats = AsyncMock(return_value={"index": {"vectorCount": 42}})

            result = runner.invoke(cli, [*base_opts, "stats"])

            assert result.exit_code == 0
            assert "42" in result.output
