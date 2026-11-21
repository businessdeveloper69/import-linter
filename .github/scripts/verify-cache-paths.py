"""Exercise native directory identity through the installed lint-imports command."""

import json
import os
import platform
import subprocess
import sys
import sysconfig
import tempfile
from pathlib import Path


def test_pair(root, label, first, second, expected):
    for index, value in enumerate((first, second), start=1):
        config = (
            "[tool.importlinter]\n"
            'root_package = "sample"\n'
            f"cache_dir = {json.dumps(str(value))}\n"
            "[[tool.importlinter.contracts]]\n"
            f'name = "Contract {index}"\n'
            'type = "acyclic_siblings"\n'
            'ancestors = ["sample"]\n'
        )
        (root / f"{index}.toml").write_text(config, encoding="utf-8")
    cli = Path(sysconfig.get_path("scripts")) / (
        "lint-imports.exe" if os.name == "nt" else "lint-imports"
    )
    result = subprocess.run(
        [str(cli), "--no-logo", "--verbose", "1.toml", "2.toml"],
        cwd=root, env={**os.environ, "PYTHONPATH": str(root), "PYTHONIOENCODING": "utf-8",
                      "TERM": "dumb", "NO_COLOR": "1"},
        capture_output=True, text=True, encoding="utf-8", check=False,
    )
    output = result.stdout + result.stderr
    if result.returncode or "Contracts: 2 kept, 0 broken." not in output:
        raise AssertionError(output)
    paths = [root / first, root / second]
    for path in paths:
        assert (path / "sample.meta.json").is_file(), path
        assert len(list(path.glob("*.data.json"))) == 1, path
    row = {
        "case": label, "first": str(first), "second": str(second),
        "same_directory": paths[0].samefile(paths[1]),
        "graphs": output.count("Built graph in "), "expected_graphs": expected,
        "contract_count": 2, "cache_files_verified": True,
    }
    print(json.dumps(row), flush=True)
    return row


def main():
    rows = []
    with tempfile.TemporaryDirectory() as path:
        root = Path(path)
        (root / "sample").mkdir()
        (root / "sample" / "__init__.py").write_text("", encoding="utf-8")
        (root / "CacheA").mkdir()
        rows.append(test_pair(root, "absolute and dotted relative", "./CacheA", root / "CacheA", 1))
        rows.append(test_pair(root, "different directories", "CacheA", "CacheB", 2))
        if os.name != "nt":
            (root / "alias").symlink_to("CacheA", target_is_directory=True)
            rows.append(test_pair(root, "directory symlink", "CacheA", "alias", 1))
            (root / "actual" / "sub").mkdir(parents=True)
            (root / "via").symlink_to("actual/sub", target_is_directory=True)
            rows.append(test_pair(root, "symlink followed by parent", "cache", "via/../cache", 2))
        case_alias = root / "cachea"
        same = case_alias.exists() and case_alias.samefile(root / "CacheA")
        if os.name == "nt":
            assert same, "Expected a case-insensitive native Windows checkout"
        rows.append(test_pair(root, "case variants", "CacheA", "cachea", 1 if same else 2))
    report = {
        "platform": platform.platform(), "python": sys.version,
        "source_sha": "e2916dc524fcae3705fee7f2a59f2f07f8edf81c", "cases": rows,
    }
    Path("native-cache-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    assert all(row["graphs"] == row["expected_graphs"] for row in rows), rows


if __name__ == "__main__":
    main()
