"""Builds the re-audit package: every git-tracked file, zipped under lb-auditor/.

    python scripts/package.py                 # -> dist/lb-auditor_<YYYYMMDD>.zip
    python scripts/package.py --out my.zip

Tracked files only, so nothing ignored by .gitignore goes in (.env, .venv, caches of the Python tooling).
That covers the data with its QC sign-off sheets, src/lb, tests, configs, prompts, analysis/plan.md, and
results/raw + results/cache (the logged judge responses, so `make reproduce` runs offline with no API key)
and results/tables. Uncommitted changes are refused: the package must match a commit.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import zipfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REFUSED = (".env",)   # never packaged, even if someone commits one


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True, text=True).stdout


def tracked_files() -> list[str]:
    files = [f for f in git("ls-files", "-z").split("\0") if f]
    bad = [f for f in files if Path(f).name.startswith(REFUSED)]
    if bad:
        raise SystemExit(f"refusing to package secret-looking files: {bad}")
    return files


def build(out: Path) -> tuple[int, str]:
    if git("status", "--porcelain", "--untracked-files=no").strip():
        raise SystemExit("uncommitted changes to tracked files: commit them first, so the package matches a commit")
    commit = git("rev-parse", "--short", "HEAD").strip()
    files = tracked_files()
    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for f in files:
            z.write(ROOT / f, f"lb-auditor/{f}")
        z.writestr("lb-auditor/PACKAGE.txt", f"Built from commit {commit} on {date.today().isoformat()}.\n"
                   "Setup and commands: README.md. Analysis plan and change log: analysis/plan.md.\n"
                   "Rebuild every table offline: make reproduce, then make stats, make stats-b, make stats-a, make stats-e5.\n")
    return len(files), commit


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--out", type=Path, default=ROOT / "dist" / f"lb-auditor_{date.today():%Y%m%d}.zip")
    args = p.parse_args()
    n, commit = build(args.out)
    print(f"wrote {args.out} ({n} files, commit {commit}, {args.out.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    sys.exit(main())
