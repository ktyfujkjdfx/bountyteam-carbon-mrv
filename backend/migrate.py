"""python -m backend.migrate -- apply SQLite migrations (idempotent)."""
import json

from .app.config import load_settings
from .app.db import migrate


def main() -> int:
    settings = load_settings()
    applied = migrate(settings.db_path)
    print(json.dumps({"db_path": str(settings.db_path), "applied_migrations": applied}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
