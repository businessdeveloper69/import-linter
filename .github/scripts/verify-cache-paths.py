"""Run the real CLI against equivalent and distinct native cache directories."""
import argparse
import json
import os
import platform
import re
import subprocess
import sys
import sysconfig
import tempfile
from pathlib import Path


def run_pair(root, label, first, second, should_share, broken=False):
    paths = [root / first, root / second]
    existed = [path.is_dir() for path in paths]
    for number, cache in enumerate((first, second), start=1):
        source, target = ("sample.a", "sample.b") if number == 1 and broken else ("sample.b", "sample.a")
        (root / f"{number}.toml").write_text(
            "[tool.importlinter]\n"
            'root_package = "sample"\n'
            f"cache_dir = {json.dumps(str(cache))}\n"
            "[[tool.importlinter.contracts]]\n"
            f'name = "Contract {number}"\n'
            'type = "forbidden"\n'
            f'source_modules = ["{source}"]\nforbidden_modules = ["{target}"]\n',
            encoding="utf-8",
        )
    cli = Path(sysconfig.get_path("scripts")) / (
        "lint-imports.exe" if os.name == "nt" else "lint-imports"
    )
    proc = subprocess.run(
        [str(cli), "--no-logo", "--verbose", "1.toml", "2.toml"], cwd=root,
        env={**os.environ, "PYTHONPATH": str(root), "PYTHONIOENCODING": "utf-8",
             "TERM": "dumb", "NO_COLOR": "1"}, capture_output=True, text=True, encoding="utf-8",
    )
    output = proc.stdout + proc.stderr
    summary = "Contracts: 1 kept, 1 broken." if broken else "Contracts: 2 kept, 0 broken."
    if proc.returncode != int(broken) or summary not in output:
        raise AssertionError(output)
    if broken:
        assert "sample.a -> sample.b (l.1)" in output, output
    for path in paths:
        assert (path / "sample.meta.json").is_file(), path
        assert len(list(path.glob("*.data.json"))) == 1, path
        assert (path / "CACHEDIR.TAG").is_file(), path
    really_same = paths[0].samefile(paths[1])
    graphs = output.count("Built graph in ")
    counts = re.search(r"Analyzed (\d+) files, (\d+) dependencies", output)
    assert counts and [int(n) for n in counts.groups()] == [3 * graphs, graphs], output
    row = dict(
        case=label, initial_dir_exists=existed, same_directory=really_same,
        graphs=graphs, expected_graphs=1 if should_share else 2,
        reported_files=int(counts[1]), reported_dependencies=int(counts[2]),
        cache_files_verified=True, linter_exit=proc.returncode, contracts=summary,
    )
    assert really_same == should_share, row
    print(json.dumps(row), flush=True)
    return row


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--filesystem", required=True, choices=["case-sensitive", "case-insensitive"])
    parser.add_argument("--label", required=True)
    parser.add_argument("--source", required=True)
    parser.add_argument("--parent", default=None)
    parser.add_argument("--expected-duplicate", action="store_true")
    args = parser.parse_args()
    rows = []
    share_case = args.filesystem == "case-insensitive"
    with tempfile.TemporaryDirectory(dir=args.parent) as path:
        root = Path(path)
        (root / "sample").mkdir()
        for module, code in {"__init__":"","a":"import sample.b\n","b":""}.items():
            (root / "sample" / f"{module}.py").write_text(code, encoding="utf-8")
        (root / "Existing").mkdir()
        assert (root / "existing").exists() == share_case
        rows.append(run_pair(root, "preexisting case variants", "Existing", "existing", share_case))
        rows.append(run_pair(root, "cold case variants", "Cold", "cold", share_case, broken=True))
        assert rows[-1]["initial_dir_exists"] == [False, False], rows[-1]
        rows.append(run_pair(root, "warm case variants", "Cold", "cold", share_case, broken=True))
        rows.append(run_pair(root, "cold nested case aliases", "Nested/Cache", "nested/cache", share_case))
        assert rows[-1]["initial_dir_exists"] == [False, False], rows[-1]
        rows.append(run_pair(root, "absolute vs dotted", "./Existing", root/"Existing", True))
        rows.append(run_pair(root, "distinct names", "DirOne", "DirTwo", False))
        if os.name != "nt":
            (root / "alias").symlink_to("Existing", target_is_directory=True)
            rows.append(run_pair(root, "symlink", "Existing", "alias", True))
            (root / "actual" / "sub").mkdir(parents=True)
            (root / "via").symlink_to("actual/sub", target_is_directory=True)
            rows.append(run_pair(root, "symlink followed by parent", "uniq", "via/../uniq", False))
    report = dict(label=args.label, platform=platform.platform(), python=sys.version,
                  filesystem=args.filesystem, source_sha=args.source, cases=rows)
    Path(f"cache-probe-{args.label}.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    mismatches = [row["case"] for row in rows if row["graphs"] != row["expected_graphs"]]
    if args.expected_duplicate:
        assert mismatches == ["preexisting case variants", "cold case variants", "warm case variants",
                              "cold nested case aliases"], mismatches
    else:
        assert not mismatches, mismatches


if __name__ == "__main__":
    main()
