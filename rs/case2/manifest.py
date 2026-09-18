"""The manifest that makes a result checkable.

It records what was read, with checksums; what the method was; and a content
hash over the scientific payload. The moment the run happened is kept out of
that hash, so replaying the same request on another machine on another day
produces the same hash - which is the only way a consumer can tell a genuine
replay from a coincidence.
"""
import subprocess
from pathlib import Path

from rs.case2.analysis import METHOD_VERSION
from rs.case2.catalog import REPO_ROOT
from rs.contracts import digest

# Directories whose state decides whether the recorded commit can reproduce the
# result. Test files are included: they are part of what defines the method.
CODE_PATHS = ("rs/case2", "rs/tests/case2")


def code_commit(repo_root=REPO_ROOT):
    """HEAD when the analysis code is committed, otherwise None.

    A dirty tree gets None rather than a commit hash. Naming a commit whose
    tree cannot reproduce these bytes would be a false provenance claim, and a
    missing value is easier to act on than a wrong one.
    """
    def git(*args):
        try:
            result = subprocess.run(
                ("git", *args), cwd=str(repo_root), capture_output=True,
                text=True, check=False)
        except OSError:
            return None
        return result.stdout.strip() if result.returncode == 0 else None

    head = git("rev-parse", "HEAD")
    if not head or len(head) != 40:
        return None
    dirty = git("status", "--porcelain", "--", *CODE_PATHS)
    if dirty is None or dirty:
        return None
    return head


def build(analysis, payload, *, generated_at=None, repo_root=REPO_ROOT):
    """Manifest for one analysis. `generated_at` stays outside the content hash."""
    manifest = {
        "schema": "rs.case2.manifest/1",
        "method_version": METHOD_VERSION,
        "code_commit": code_commit(repo_root),
        "dataset": {
            "root": "data",
            "files": [
                {
                    "path": source.relative_path,
                    "sha256": source.sha256,
                    "size_bytes": source.size_bytes,
                    "role": source.role,
                }
                for source in analysis.sources
            ],
        },
        "parameters": payload["parameters"],
        "request": payload["request"],
        "content_sha256": digest(payload),
        "content_note": (
            "sha256 over the canonical JSON of analysis.json; it excludes the run "
            "time, so an identical request reproduces an identical hash"
        ),
    }
    if generated_at is not None:
        manifest["generated_at"] = generated_at
    return manifest


def outputs_are_safe(directory, data_root):
    """Refuse to write results into the supplied dataset."""
    directory = Path(directory).resolve()
    data_root = Path(data_root).resolve()
    return not (directory == data_root or directory.is_relative_to(data_root))
