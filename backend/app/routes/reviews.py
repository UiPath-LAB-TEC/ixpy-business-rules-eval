from fastapi import APIRouter

from ..models.schemas import AnnotationPayload, ReviewPayload
from ..services import query


router = APIRouter(prefix="/api/reviews", tags=["reviews"])


@router.get("/{filename}/{rule_name}")
def get_review(filename: str, rule_name: str):
    return query.get_review(filename, rule_name)


@router.post("/{filename}/{rule_name}")
def save_review(filename: str, rule_name: str, payload: ReviewPayload):
    return query.save_review(filename, rule_name, payload.model_dump())


@router.get("/{filename}/{rule_name}/annotations")
def list_annotations(filename: str, rule_name: str):
    return query.list_annotations(filename, rule_name)


@router.post("/{filename}/{rule_name}/annotations")
def save_annotation(filename: str, rule_name: str, payload: AnnotationPayload):
    return query.save_annotation(filename, rule_name, payload.model_dump())


@router.post("/{filename}/{rule_name}/recompute")
def recompute_with_annotations(filename: str, rule_name: str):
    return query.recompute_with_annotations(filename, rule_name)
