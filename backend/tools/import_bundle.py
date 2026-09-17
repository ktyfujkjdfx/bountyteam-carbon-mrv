"""python -m backend.tools.import_bundle --bundle <bundle_dir> [--evidence <file>] [--computation-mode MODE]

RS handoff entry point. Validates the bundle (schema, semantics, geometry, safe paths,
artifact and source hashes), stores canonical JCS bytes, computes evidence_hash and the
policy decision. Prints the accepted record as JSON; exit code 2 on rejection.
Freeze intents for FREEZE_REQUESTED are planned by the worker, never by this command.
"""
import argparse
import json
import sys
from pathlib import Path

from ..app.config import load_settings
from ..app.context import create_context
from ..app.evidence import EvidenceRejected
from ..app.ingest import import_evidence


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--bundle", required=True, help="Bundle root containing source-index.json and artifacts")
    parser.add_argument("--evidence", help="Evidence JSON (default <bundle>/verification.json)")
    parser.add_argument("--computation-mode", choices=["COMPUTED", "CACHED_REPLAY"], default="CACHED_REPLAY")
    parser.add_argument("--plot-id", help="Reject evidence for any other plot")
    args = parser.parse_args(argv)
    bundle = Path(args.bundle)
    evidence_path = Path(args.evidence) if args.evidence else bundle / "verification.json"
    ctx = create_context(load_settings())
    try:
        result = import_evidence(ctx, evidence_path.read_bytes(), bundle, computation_mode=args.computation_mode,
                                 expected_plot_id=args.plot_id)
    except (EvidenceRejected, OSError) as exc:
        message = exc.message if isinstance(exc, EvidenceRejected) else "Cannot read evidence file"
        details = exc.details if isinstance(exc, EvidenceRejected) else {}
        print(json.dumps({"accepted": False, "error": {"code": "INVALID_EVIDENCE", "message": message,
                                                        "details": details}}, ensure_ascii=False), file=sys.stderr)
        return 2
    print(json.dumps({"accepted": True, "created": result.created, "verification_id": result.verification_id,
                      "evidence_hash": result.evidence_hash, "decision": result.decision, "reason": result.reason,
                      "decision_hash": result.decision_hash}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
