from fastapi import APIRouter

from ..services import query


router = APIRouter(prefix="/api/runs", tags=["runs"])


@router.get("")
def list_runs(limit: int = 50):
    return query.list_runs(limit)

