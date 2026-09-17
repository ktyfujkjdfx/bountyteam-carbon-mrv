"""CLI: python -m rs.verify --request <request.json> --output <bundle_dir>

Reads a schema-valid rs-request.json plus its cached local source files (never
the network) and writes a schema-valid VerificationEvidence bundle. This is
the reproducible, offline-capable entry point Backend imports via
`python -m backend.tools.import_bundle --bundle <bundle_dir>`.
"""
import argparse
import re
import subprocess
import sys

from rs import bundle, pipeline
from rs.contracts import check_schema, digest, read_json, validate_evidence, validate_geometry

COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
# rs/bundles is this command's own output, so its state says nothing about
# whether the code that produced it is committed.
CODE_PATHS = ("rs", ":(exclude)rs/bundles")


def _git(*args):
    try:
        out = subprocess.run(["git", *args], capture_output=True, text=True, timeout=10, check=True)
        return out.stdout.strip()
    except Exception:
        return None


def resolve_code_commit(explicit=None):
    """The commit whose code reproduces this bundle, or None if there isn't one.

    `method.code_commit` is a reproducibility claim: it must name a commit that
    actually contains the pipeline that produced these bytes. So an explicit
    value (the two-step release flow in rs/README.md) is used as given, and
    otherwise HEAD is used *only* when the RS code is committed. With
    uncommitted changes no commit reproduces the bundle, and the schema's null
    is the truthful answer - better than pointing at a commit that cannot.
    """
    if explicit is not None:
        if not COMMIT_RE.match(explicit):
            raise ValueError(f"--code-commit must be a full 40-hex commit sha, got {explicit!r}")
        return explicit
    head = _git("rev-parse", "HEAD")
    if head is None or not COMMIT_RE.match(head):
        return None
    dirty = _git("status", "--porcelain", "--", *CODE_PATHS)
    if dirty is None or dirty:
        print(
            "rs.verify: RS code has uncommitted changes; recording code_commit=null "
            "instead of a commit that cannot reproduce this bundle.",
            file=sys.stderr,
        )
        return None
    return head


def run(request_path, output_dir, *, code_commit=None):
    request = read_json(request_path)
    check_schema(request, "rs-request.schema.json")
    validate_geometry(request["geometry"])
    if digest(request["geometry"]) != request["plot_geometry_hash"]:
        raise ValueError("request plot_geometry_hash does not match its geometry")

    evidence, artifacts_payload = pipeline.compute_evidence(
        request, code_commit=resolve_code_commit(code_commit)
    )
    evidence = bundle.write_bundle(evidence, artifacts_payload, request, output_dir)

    # Self-check with the same reference validator Backend uses, before
    # declaring the bundle done, so a broken bundle is never handed off silently.
    validate_evidence(evidence, output_dir, request["geometry"])
    return evidence


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", required=True, help="Path to a rs-request.schema.json-valid file")
    parser.add_argument("--output", required=True, help="Bundle output directory")
    parser.add_argument(
        "--code-commit",
        help="Full 40-hex sha of the commit containing the pipeline code (two-step release flow)",
    )
    args = parser.parse_args(argv)

    evidence = run(args.request, args.output, code_commit=args.code_commit)
    print(f"outcome={evidence['outcome']} plot_id={evidence['plot_id']} bundle={args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
