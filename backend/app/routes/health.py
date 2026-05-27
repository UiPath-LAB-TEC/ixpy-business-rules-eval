from fastapi import APIRouter

from ..services import query


router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
def health():
    return query.health()

