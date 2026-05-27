from fastapi import APIRouter

from ..services import query


router = APIRouter(prefix="/api/training-exceptions", tags=["training-exceptions"])


@router.get("")
def list_training_exceptions():
    return query.list_training_exceptions()


@router.post("/export")
def export_training_exceptions():
    return query.export_training_exceptions()


@router.delete("/{filename}")
def remove_training_exception(filename: str, rule_name: str | None = None):
    return query.remove_training_exception(filename, rule_name)
