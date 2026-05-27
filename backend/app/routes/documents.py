from fastapi import APIRouter

from ..config import get_settings
from ..services import query


router = APIRouter(prefix="/api/documents", tags=["documents"])


@router.get("")
def list_documents(
    search: str | None = None,
    status: str | None = None,
    rule: str | None = None,
    review_status: str | None = None,
    warning: str | None = None,
    sort: str = "highest_value",
    direction: str | None = None,
    limit: int | None = None,
    offset: int = 0,
):
    page_size = limit or get_settings().page_size
    return query.list_documents(search, status, rule, review_status, warning, sort, direction, page_size, offset)


@router.get("/training-exceptions")
def list_training_exceptions():
    return query.list_training_exceptions()


@router.post("/training-exceptions/export")
def export_training_exceptions():
    return query.export_training_exceptions()


@router.get("/{filename}")
def document_detail(filename: str):
    return query.document_detail(filename)


@router.get("/{filename}/file")
def document_file(filename: str):
    return query.document_file(filename)


@router.post("/{filename}/training-exception")
def copy_document_to_training_exception(filename: str, rule_name: str | None = None):
    return query.copy_document_to_training_exception(filename, rule_name)


@router.post("/{filename}/archive")
def archive_document(filename: str, rule_name: str | None = None):
    return query.archive_document(filename, rule_name)


@router.delete("/{filename}/training-exception")
def remove_training_exception(filename: str, rule_name: str | None = None):
    return query.remove_training_exception(filename, rule_name)
