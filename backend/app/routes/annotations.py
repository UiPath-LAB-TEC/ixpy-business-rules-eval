from fastapi import APIRouter

from ..models.schemas import AnnotationBatchPayload
from ..services import query


router = APIRouter(prefix="/api/annotations", tags=["annotations"])


@router.get("/{filename}/{rule_name}")
def list_annotations(filename: str, rule_name: str):
    return query.list_annotations(filename, rule_name)


@router.post("/{filename}/{rule_name}")
def save_annotations(filename: str, rule_name: str, payload: AnnotationBatchPayload):
    return query.save_annotations(filename, rule_name, payload.model_dump())


@router.post("/{filename}/{rule_name}/recompute")
def recompute_with_annotations(filename: str, rule_name: str, payload: AnnotationBatchPayload):
    return query.recompute_with_annotations(filename, rule_name, payload.model_dump())
