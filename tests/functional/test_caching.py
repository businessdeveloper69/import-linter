import os
import tempfile
from pathlib import Path

import pytest
from click.testing import CliRunner

from importlinter import cli

this_directory = Path(__file__).parent
assets_directory = this_directory / ".." / "assets"

testpackage_directory = assets_directory / "testpackage"


class TestCaching:
    def test_no_cache(self):
        os.chdir(testpackage_directory)

        with tempfile.TemporaryDirectory() as cache_dir:
            cli.lint_imports(cache_dir=cache_dir, no_cache=True)

            meta_file = Path(cache_dir) / "testpackage.meta.json"
            # Blake2B 20-character hash of "testpackage".
            data_file = Path(cache_dir) / "216a42e0de035f511ad815351348f07aa91057c2.data.json"

            assert not meta_file.exists()
            assert not data_file.exists()

    def test_supplied_cache_dir(self):
        os.chdir(testpackage_directory)

        with tempfile.TemporaryDirectory() as cache_dir:
            cli.lint_imports(cache_dir=cache_dir, is_debug_mode=True)

            meta_file = Path(cache_dir) / "testpackage.meta.json"
            # Blake2B 20-character hash of "testpackage".
            data_file = Path(cache_dir) / "216a42e0de035f511ad815351348f07aa91057c2.data.json"

            assert meta_file.exists()
            assert data_file.exists()

    @pytest.mark.parametrize(
        "options, cache_dirs",
        [
            ([], ["ini-cache", "toml-cache"]),
            (["--cache-dir", "cli-cache"], ["cli-cache"]),
            (["--no-cache"], []),
        ],
    )
    def test_configured_cache_directories(self, tmp_path, monkeypatch, options, cache_dirs):
        monkeypatch.chdir(tmp_path)
        package = tmp_path / "example"
        package.mkdir()
        (package / "__init__.py").touch()
        (tmp_path / "first.ini").write_text(
            "[importlinter]\n"
            "root_package = example\n"
            "cache_dir = ini-cache\n"
            "[importlinter:contract:first]\n"
            "name = First\n"
            "type = acyclic_siblings\n"
            "ancestors = example\n"
        )
        (tmp_path / "second.toml").write_text(
            "[tool.importlinter]\n"
            'root_package = "example"\n'
            'cache_dir = "toml-cache"\n'
            "[[tool.importlinter.contracts]]\n"
            'name = "Second"\n'
            'type = "acyclic_siblings"\n'
            'ancestors = ["example"]\n'
        )

        result = CliRunner().invoke(
            cli.lint_imports_command, ["first.ini", "second.toml", *options]
        )

        assert result.exit_code == cli.EXIT_STATUS_SUCCESS, result.output
        assert "Contracts: 2 kept, 0 broken." in result.output
        assert sorted(tmp_path.glob("*/example.meta.json")) == [
            tmp_path / directory / "example.meta.json" for directory in cache_dirs
        ]
        if len(cache_dirs) == 2:
            assert "Total 2 config files, 2 import graphs." in result.output
        else:
            assert "Config files" not in result.output  # Both contracts share a single graph.

    @pytest.mark.parametrize("value", ['""', "false", '["first", "second"]'])
    def test_rejects_invalid_cache_dir(self, tmp_path, monkeypatch, value):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "pyproject.toml").write_text(
            "[tool.importlinter]\n"
            'root_package = "example"\n'
            f"cache_dir = {value}\n"
            "[[tool.importlinter.contracts]]\n"
            'name = "Example"\n'
            'type = "acyclic_siblings"\n'
            'ancestors = ["example"]\n'
        )

        result = CliRunner().invoke(cli.lint_imports_command)

        assert result.exit_code == cli.EXIT_STATUS_ERROR
        assert "cache_dir must be a non-empty directory path." in result.output
