from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, Field


class ReadinessPosture(StrEnum):
    READY = "ready"
    READY_WITH_NOTES = "ready_with_notes"
    CONTROLLED_FOLLOW_UP = "controlled_follow_up"
    HOLD = "hold"
    UNKNOWN = "unknown"


class SystemVariant(StrEnum):
    PDM = "pdm"
    GDM = "gdm"
    PDM_GDM = "pdmg"
    UNKNOWN = "unknown"


class SourceDocument(BaseModel):
    label: str
    path: str
    pages: int
    sha256: str


class Project(BaseModel):
    project_name: str | None = None
    substation: str | None = None
    customer: str | None = None
    country: str | None = None
    voltage: str | None = None
    contract_number: str | None = None
    manufacturing_number: str | None = None


class Equipment(BaseModel):
    system_type: str | None = None
    equipment: str | None = None
    equipment_tag: str | None = None
    ocu_model: str | None = None
    operating_frequency: str | None = None
    number_of_ocus: str | None = None
    sensor_count: int | None = None
    gdm_module_count: int | None = None


class FatContext(BaseModel):
    document_no: str | None = None
    revision: str | None = None
    fat_date: str | None = None
    date_range: str | None = None
    venue: str | None = None
    inspection_type: str | None = None
    tester: str | None = None
    project_owner: str | None = None


class TestItem(BaseModel):
    code: str
    name: str
    status: str | None = None
    page: int | None = None
    confidence: float = Field(default=0.7, ge=0.0, le=1.0)


class TestCoverage(BaseModel):
    sections: dict[str, str] = Field(default_factory=dict)
    tests: list[TestItem] = Field(default_factory=list)
    detected_test_count: int = 0
    passed_count: int | None = None
    failed_count: int | None = None
    na_count: int | None = None


class FinalCheck(BaseModel):
    name: str
    result: str | None = None
    note: str | None = None
    page: int | None = None


class DocumentReview(BaseModel):
    summary: str | None = None
    referenced_document_count: int | None = None
    rows_with_no_changes: int | None = None


class Observation(BaseModel):
    text: str
    owner: str | None = None
    status: str | None = None
    source_page: int | None = None


class EvidenceNote(BaseModel):
    text: str
    source_page: int | None = None


class PictureEvidence(BaseModel):
    path: str
    caption: str | None = None


class ActionItem(BaseModel):
    action: str
    owner: str | None = None
    state: str | None = None
    source_page: int | None = None


class SystemBuildItem(BaseModel):
    item: str
    detail: str | None = None


class AddressingRow(BaseModel):
    name: str
    address: str | None = None
    cabinet: str | None = None


class SystemBuild(BaseModel):
    hardware_baseline: list[SystemBuildItem] = Field(default_factory=list)
    software_baseline: list[SystemBuildItem] = Field(default_factory=list)
    addressing: list[AddressingRow] = Field(default_factory=list)


class ExportManifest(BaseModel):
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    template_version: str = "qualitrol-fat-summary-v0.1"
    user_edits_made: bool = False


class FatSummary(BaseModel):
    source_documents: list[SourceDocument] = Field(default_factory=list)
    project: Project = Field(default_factory=Project)
    equipment: Equipment = Field(default_factory=Equipment)
    fat_context: FatContext = Field(default_factory=FatContext)
    test_coverage: TestCoverage = Field(default_factory=TestCoverage)
    final_checks: list[FinalCheck] = Field(default_factory=list)
    document_review: DocumentReview = Field(default_factory=DocumentReview)
    observations: list[Observation] = Field(default_factory=list)
    evidence_notes: list[EvidenceNote] = Field(default_factory=list)
    picture_evidence: list[PictureEvidence] = Field(default_factory=list)
    next_actions: list[ActionItem] = Field(default_factory=list)
    system_build: SystemBuild = Field(default_factory=SystemBuild)
    system_variant: SystemVariant = SystemVariant.UNKNOWN
    readiness_posture: ReadinessPosture = ReadinessPosture.UNKNOWN
    export_manifest: ExportManifest = Field(default_factory=ExportManifest)

    def write_json(self, path: str | Path) -> None:
        Path(path).write_text(self.model_dump_json(indent=2), encoding="utf-8")
