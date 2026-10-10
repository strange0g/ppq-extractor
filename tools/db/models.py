"""Typed Pydantic v2 domain models for PPQ Extractor SQLite question bank."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class DomainBaseModel(BaseModel):
    """Base domain model providing dict subscripting and .to_dict() compatibility."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    def __getitem__(self, item: str) -> Any:
        try:
            return getattr(self, item)
        except AttributeError:
            raise KeyError(item)

    def __setitem__(self, key: str, value: Any) -> None:
        setattr(self, key, value)

    def __contains__(self, item: object) -> bool:
        return hasattr(self, str(item))

    def get(self, item: str, default: Any = None) -> Any:
        return getattr(self, item, default)

    def to_dict(self) -> dict[str, Any]:
        """Serialize model to a standard python dictionary."""
        return self.model_dump()

    def keys(self) -> Any:
        return self.__dict__.keys()

    def values(self) -> Any:
        return self.__dict__.values()

    def items(self) -> Any:
        return self.__dict__.items()


class TopicModel(DomainBaseModel):
    """Syllabus curriculum topic definition and question counts."""

    topic_code: str
    title: str
    syllabus: str
    question_count: int = 0
    part_count: int = 0


class SliceModel(DomainBaseModel):
    """Bounding box coordinate slice of a question or Question Part."""

    id: int | None = None
    question_id: str
    part_id: str | None = None
    kind: str
    page: int
    ymin: float
    ymax: float
    xmin: float = 0.0
    xmax: float = 1000.0
    sequence: int = 0


class QuestionPartModel(DomainBaseModel):
    """Question Part with labels, marks, isolated asset path, and topic tags."""

    id: str
    question_id: str
    label: str
    part_label: str | None = None
    marks: int = 0
    part_image_path: str | None = None
    asset_path: str | None = None
    has_preamble_context: bool = False
    topics: list[str] = Field(default_factory=list)

    # Context fields when queried with question/paper joins
    question_number: int | None = None
    paper_id: str | None = None
    preamble_image_path: str | None = None
    composite_image_path: str | None = None
    syllabus: str | None = None
    year: int | None = None
    session: str | None = None
    session_slug: str | None = None
    component: int | None = None
    variant: int | None = None
    output_dir: str | None = None


class QuestionModel(DomainBaseModel):
    """Past paper question item, composite assets, and nested Question Parts."""

    id: str
    paper_id: str
    question_number: int
    total_marks: int = 0
    has_preamble: bool = False
    composite_image_path: str | None = None
    preamble_image_path: str | None = None
    syllabus: str | None = None
    year: int | None = None
    session: str | None = None
    session_slug: str | None = None
    component: int | None = None
    variant: int | None = None
    output_dir: str | None = None
    topics: list[str] = Field(default_factory=list)
    parts: list[QuestionPartModel] = Field(default_factory=list)


class PaperModel(DomainBaseModel):
    """Past paper metadata, verification status, and mark totals."""

    id: str
    syllabus: str
    year: int
    session: str
    session_slug: str
    component: int
    variant: int | None = None
    source_pdf: str
    status: str
    total_pages: int
    mode: str
    expected_marks: int
    extracted_marks: int | None = None
    output_dir: str
    extracted_at: str | None = None
    verified_at: str | None = None
    verifier_notes: str | None = None
    questions_count: int | None = None
    calculated_marks: int | None = None


class QuestionQueryFilter(DomainBaseModel):
    """Query filter parameters for question and Question Part lookups."""

    topic_code: str | None = None
    syllabus: str | None = None
    component: int | None = None
    variant: int | None = None
    year: int | None = None
    year_min: int | None = None
    year_max: int | None = None
    session: str | None = None
    min_marks: int | None = None
    max_marks: int | None = None
    paper_id: str | None = None
    question_id: str | None = None
    limit: int | None = None
    offset: int | None = None
