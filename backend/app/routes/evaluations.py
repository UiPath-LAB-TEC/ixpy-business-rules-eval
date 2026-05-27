from fastapi import APIRouter

from ..services import query


router = APIRouter(prefix="/api/evaluations", tags=["evaluations"])


@router.get("/{filename}")
def evaluations(filename: str):
    return query.evaluations(filename)


@router.get("/{filename}/{rule_name}/explanation")
def explanation(filename: str, rule_name: str):
    return query.explanation(filename, rule_name)

