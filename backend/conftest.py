"""Backend role tests run only when backend/ is targeted explicitly: `python -m pytest backend -q`.

The shared root command `python -m pytest -q` must keep validating only the frozen
contract baseline (68 tests) and must not require backend/requirements-backend.txt.
"""
import warnings
from pathlib import Path

HERE = Path(__file__).resolve().parent

# Third-party deprecations raised inside starlette.testclient on import, not by backend code.
warnings.filterwarnings("ignore", message="Using `httpx` with `starlette.testclient`")
warnings.filterwarnings("ignore", message="The anyio.abc.BlockingPortal alias is deprecated")
warnings.filterwarnings("ignore", message="websockets.legacy is deprecated")  # imported by web3.py


def _targets_backend(config) -> bool:
    for arg in config.args:
        candidate = Path(str(arg).split("::")[0])
        if not candidate.is_absolute():
            candidate = Path(config.invocation_params.dir) / candidate
        if candidate.resolve().is_relative_to(HERE):
            return True
    return False


def pytest_configure(config):
    # web3.py imports websockets.legacy lazily during tests; pytest re-applies ini filters per test.
    config.addinivalue_line("filterwarnings", "ignore:websockets.legacy is deprecated:DeprecationWarning")


def pytest_ignore_collect(collection_path, config):
    if Path(collection_path).resolve().is_relative_to(HERE) and not _targets_backend(config):
        return True
    return None
