from __future__ import annotations

from fat_summary_app.models import FatSummary
from fat_summary_app.models.report import ReadinessPosture, SystemVariant


EDITABLE_FIELDS = {
    "project.project_name": "Project",
    "project.substation": "Substation",
    "project.customer": "Customer",
    "project.country": "Country",
    "project.voltage": "Voltage",
    "project.contract_number": "Contract No.",
    "project.manufacturing_number": "Manufacturing No.",
    "equipment.system_type": "System Type",
    "equipment.equipment": "Equipment",
    "equipment.equipment_tag": "Equipment Tag",
    "equipment.ocu_model": "Total OCU",
    "equipment.ocu_channel_count": "OCU Channel",
    "equipment.operating_frequency": "Frequency",
    "equipment.sensor_count": "GDM Sensor Count",
    "equipment.gdm_module_count": "GDM Module Count",
    "fat_context.document_no": "Document No.",
    "fat_context.revision": "Revision",
    "fat_context.fat_date": "FAT Date",
    "fat_context.date_range": "Date Range",
    "fat_context.venue": "Venue",
    "fat_context.inspection_type": "Inspection Type",
    "fat_context.tester": "Tester",
    "fat_context.project_owner": "Project Owner",
    "test_coverage.detected_test_count": "Total Checks",
    "test_coverage.passed_count": "Passed",
    "test_coverage.failed_count": "Failed",
    "test_coverage.na_count": "N/A",
    "test_coverage.completion_percent": "Completion %",
    "final_checks.ups_result": "UPS / FINAL CHECKS result",
    "final_checks.ups_note": "UPS / FINAL CHECKS note",
}

INTEGER_FIELDS = {
    "equipment.sensor_count",
    "equipment.gdm_module_count",
    "test_coverage.detected_test_count",
    "test_coverage.passed_count",
    "test_coverage.failed_count",
    "test_coverage.na_count",
    "test_coverage.completion_percent",
}


def get_editable_values(summary: FatSummary) -> dict[str, str]:
    values: dict[str, str] = {}
    counts = _review_counts(summary)
    for path in EDITABLE_FIELDS:
        value = _get_special_path(summary, path) if path.startswith("final_checks.") else _get_path(summary, path)
        if path == "test_coverage.passed_count":
            value = counts["passed"]
        if path == "test_coverage.failed_count":
            value = counts["failed"]
        if path == "test_coverage.na_count":
            value = counts["na"]
        if path == "test_coverage.completion_percent":
            value = counts["completion"]
        values[path] = "" if value is None else str(value)
    values["system_variant"] = summary.system_variant.value
    values["readiness_posture"] = summary.readiness_posture.value
    return values


def apply_review_edits(summary: FatSummary, values: dict[str, str]) -> FatSummary:
    updated = summary.model_copy(deep=True)
    for path in EDITABLE_FIELDS:
        value: str | int | None = _clean(values.get(path))
        if path in INTEGER_FIELDS:
            value = _clean_int(values.get(path))
        if path.startswith("final_checks."):
            _set_special_path(updated, path, value)
        else:
            _set_path(updated, path, value)

    variant = values.get("system_variant")
    if variant:
        updated.system_variant = SystemVariant(variant)

    posture = values.get("readiness_posture")
    if posture:
        updated.readiness_posture = ReadinessPosture(posture)

    updated.export_manifest.user_edits_made = True
    return updated


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _clean_int(value: str | None) -> int | None:
    cleaned = _clean(value)
    if cleaned is None:
        return None
    return int(cleaned.replace(",", ""))


def _get_path(summary: FatSummary, path: str) -> object:
    current: object = summary
    for part in path.split("."):
        current = getattr(current, part)
    return current


def _set_path(summary: FatSummary, path: str, value: str | int | None) -> None:
    parts = path.split(".")
    current: object = summary
    for part in parts[:-1]:
        current = getattr(current, part)
    setattr(current, parts[-1], value)


def _get_special_path(summary: FatSummary, path: str) -> object:
    check = next((item for item in summary.final_checks if "ups" in item.name.lower()), None)
    if not check:
        return None
    if path == "final_checks.ups_result":
        return check.result
    if path == "final_checks.ups_note":
        return check.note
    return None


def _set_special_path(summary: FatSummary, path: str, value: str | int | None) -> None:
    from fat_summary_app.models.report import FinalCheck

    check = next((item for item in summary.final_checks if "ups" in item.name.lower()), None)
    if not check:
        check = FinalCheck(name="UPS Battery Charge Status")
        summary.final_checks.append(check)
    if path == "final_checks.ups_result":
        check.result = None if value is None else str(value).upper()
    if path == "final_checks.ups_note":
        check.note = None if value is None else str(value)


def _review_counts(summary: FatSummary) -> dict[str, int]:
    total = summary.test_coverage.detected_test_count or len(summary.test_coverage.tests)
    na = sum(1 for item in summary.test_coverage.tests if (item.status or "").lower() == "n/a")
    failed = sum(1 for item in summary.test_coverage.tests if (item.status or "").lower() in {"fail", "failed"})
    applicable = max(total - na, 0)
    passed = max(applicable - failed, 0)
    return {
        "passed": summary.test_coverage.passed_count if summary.test_coverage.passed_count is not None else passed,
        "failed": summary.test_coverage.failed_count if summary.test_coverage.failed_count is not None else failed,
        "na": summary.test_coverage.na_count if summary.test_coverage.na_count is not None else na,
        "completion": summary.test_coverage.completion_percent if summary.test_coverage.completion_percent is not None else min(round((passed / applicable) * 100) if applicable else 100, 100),
    }
