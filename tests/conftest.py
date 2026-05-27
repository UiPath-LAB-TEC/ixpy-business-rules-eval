from __future__ import annotations

import os
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
PARENT = ROOT.parent
sys.path.insert(0, str(ROOT))


def make_fixture(tmp_path: Path) -> tuple[Path, Path]:
    from scripts.create_fixture_db import create_fixture

    db_path = tmp_path / "settlement_fixture.db"
    doc_root = tmp_path / "docs"
    create_fixture(db_path, doc_root)
    os.environ["BUSINESS_RULE_DB"] = str(db_path)
    os.environ["BUSINESS_RULE_DOCUMENT_ROOT"] = str(doc_root)
    return db_path, doc_root
