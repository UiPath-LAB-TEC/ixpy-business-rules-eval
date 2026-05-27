from __future__ import annotations

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.app.db import apply_migrations


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True)
    args = parser.parse_args()
    applied = apply_migrations(Path(args.db))
    print("\n".join(applied) if applied else "no migrations applied")


if __name__ == "__main__":
    main()
