from fastapi import APIRouter

from ..services import query


router = APIRouter(prefix="/api/analytics", tags=["analytics"])


@router.get("")
def analytics():
    return query.analytics()

