from __future__ import annotations

from pydantic import BaseModel


class ReviewPayload(BaseModel):
    status: str = "unreviewed"
    root_cause: str | None = None
    notes: str = ""


class AnnotationPayload(BaseModel):
    detail_id: int | None = None
    evidence_role: str | None = None
    detail_type: str | None = None
    source_field: str | None = None
    source_field_id: str | None = None
    row_index: int | None = None
    column_index: int | None = None
    corrected_amount: float | None = None
    include_in_rule: bool | None = None
    include_row: bool | None = None
    root_cause: str | None = None
    notes: str = ""


class AnnotationBatchPayload(BaseModel):
    annotations: list[AnnotationPayload] = []
