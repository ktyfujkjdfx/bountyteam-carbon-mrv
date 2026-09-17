"""Regenerate the committed bundles so method.code_commit is a real claim.

`method.code_commit` must name a commit that actually contains the pipeline
that produced the bundle. A single commit cannot do that: the bundle has to be
generated *before* it is committed, so whatever sha is available while
generating is the one from the run before. Hence two steps:

    step 1  commit the generator and its inputs (rs/*.py, rs/sources/, configs)
    step 2  python -m rs.release          <- regenerates every bundle, stamping
                                             the step-1 sha into code_commit
    step 3  commit ONLY rs/bundles/       <- the artifacts, as their own commit

After step 3 the recorded sha points at step 1, whose tree contains exactly the
code and inputs that reproduce these bytes, and the artifact commit changes no
code. This command refuses to run unless step 1 is actually done, because a
dirty tree would stamp a sha that reproduces nothing.

Usage: python -m rs.release [--allow-dirty-bundles] [scenario ...]
"""
import argparse
import subprocess
import sys
from pathlib import Path

from rs import verify

ROOT = Path(__file__).resolve().parents[1]
BUNDLES = [
    ("no_change", "request_no_change.json"),
    ("fire", "request_fire.json"),
    ("evia_reserve_no_change", "request_evia_reserve_no_change.json"),
]


def _git(*args):
    out = subprocess.run(["git", *args], capture_output=True, text=True, timeout=30, check=True, cwd=ROOT)
    return out.stdout.strip()


def code_commit_for_release():
    """HEAD, but only once every code/input change is committed (step 1)."""
    dirty = _git("status", "--porcelain", "--", *verify.CODE_PATHS)
    if dirty:
        raise SystemExit(
            "rs.release: step 1 is not done - these RS code/input paths have uncommitted changes:\n"
            f"{dirty}\n"
            "Commit them first, then re-run. rs/bundles/ is excluded: it is this command's output."
        )
    return _git("rev-parse", "HEAD")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("scenarios", nargs="*", help="Bundle names to rebuild (default: all committed bundles)")
    args = parser.parse_args(argv)

    commit = code_commit_for_release()
    wanted = args.scenarios or [name for name, _ in BUNDLES]
    print(f"rs.release: stamping code_commit={commit}")
    for name, request_name in BUNDLES:
        if name not in wanted:
            continue
        evidence = verify.run(
            ROOT / "rs" / "configs" / request_name,
            ROOT / "rs" / "bundles" / name,
            code_commit=commit,
        )
        assert evidence["method"]["code_commit"] == commit
        print(f"  {name}: outcome={evidence['outcome']} code_commit={commit}")
    print("rs.release: now commit ONLY rs/bundles/ (step 3).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
