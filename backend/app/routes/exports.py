from fastapi import APIRouter
from fastapi.responses import Response

from ..services import query


router = APIRouter(prefix="/api/exports", tags=["exports"])


@router.get("/failed-rules.csv")
def failed_rules_csv():
    return Response(
        query.failed_rules_csv(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=failed-rules.csv"},
    )

