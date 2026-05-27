from __future__ import annotations

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from business_rules.settlement_statement import process_all_documents


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True)
    parser.add_argument("--document-root")
    args = parser.parse_args()
    run_id = process_all_documents(args.db, args.document_root)
    print(f"run_id={run_id}")


if __name__ == "__main__":
    main()
