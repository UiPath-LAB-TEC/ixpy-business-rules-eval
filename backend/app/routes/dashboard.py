from fastapi import APIRouter

from ..services import query


router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("")
def dashboard():
    return query.dashboard()

