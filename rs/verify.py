"""CLI: python -m rs.verify --request <request.json> --output <bundle_dir>

Reads a schema-valid rs-request.json plus its cached local source files (never
the network) and writes a schema-valid VerificationEvidence bundle. This is
the reproducible, offline-capable entry point Backend imports via
`python -m backend.tools.import_bundle --bundle <bundle_dir>`.
"""
import argparse
import subprocess
import sys

from rs import bundle, pipeline
from rs.contracts import check_schema, digest, read_json, validate_evidence, validate_geometry


def _git_commit():
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, timeout=5, check=True
        )
        return out.stdout.strip()
    except Exception:
        return None


def run(request_path, output_dir):
    request = read_json(request_path)
    check_schema(request, "rs-request.schema.json")
    validate_geometry(request["geometry"])
    if digest(request["geometry"]) != request["plot_geometry_hash"]:
        raise ValueError("request plot_geometry_hash does not match its geometry")

    evidence, artifacts_payload = pipeline.compute_evidence(request, code_commit=_git_commit())
    evidence = bundle.write_bundle(evidence, artifacts_payload, request, output_dir)

    # Self-check with the same reference validator Backend uses, before
    # declaring the bundle done, so a broken bundle is never handed off silently.
    validate_evidence(evidence, output_dir, request["geometry"])
    return evidence


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", required=True, help="Path to a rs-request.schema.json-valid file")
    parser.add_argument("--output", required=True, help="Bundle output directory")
    args = parser.parse_args(argv)

    evidence = run(args.request, args.output)
    print(f"outcome={evidence['outcome']} plot_id={evidence['plot_id']} bundle={args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
