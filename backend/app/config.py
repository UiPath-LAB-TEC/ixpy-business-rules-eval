from dataclasses import dataclass
import os
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    db_path: Path
    document_root: Path
    page_size: int
    cors_origins: tuple[str, ...]


def get_settings() -> Settings:
    db_path = Path(os.environ.get("BUSINESS_RULE_DB", "tests/fixtures/settlement_fixture.db"))
    document_root = Path(os.environ.get("BUSINESS_RULE_DOCUMENT_ROOT", "tests/fixtures/docs"))
    page_size = int(os.environ.get("BUSINESS_RULE_PAGE_SIZE", "25"))
    origins = tuple(
        origin.strip()
        for origin in os.environ.get(
            "BUSINESS_RULE_CORS_ORIGINS",
            "http://127.0.0.1:5173,http://localhost:5173,http://127.0.0.1:5174,http://localhost:5174",
        ).split(",")
        if origin.strip()
    )
    return Settings(
        db_path=db_path,
        document_root=document_root,
        page_size=page_size,
        cors_origins=origins,
    )
