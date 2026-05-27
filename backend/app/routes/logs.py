from fastapi import APIRouter

from ..config import get_settings
from ..services import query


router = APIRouter(prefix="/api/logs", tags=["logs"])


@router.get("")
def logs(level: str | None = None, limit: int | None = None, offset: int = 0):
    return query.logs(level, limit or get_settings().page_size, offset)

