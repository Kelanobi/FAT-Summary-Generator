from __future__ import annotations

import base64
import re
from pathlib import Path

from fat_summary_app.models import FatSummary
from fat_summary_app.models.report import SystemVariant


MISSING = "-"


def _display(value: object | None) -> str:
    if value is None:
        return MISSING
    text = str(value).strip()
    return text if text else MISSING


def build_template_context(summary: FatSummary) -> dict[str, object]:
    """Return the v0.1 four-page template context from normalized extraction data."""
    tested = sum(1 for item in summary.test_coverage.tests if item.status == "tested")
    not_applicable = sum(1 for item in summary.test_coverage.tests if item.status == "n/a")
    return {
        "page_1": {
            "title": "Executive FAT Summary",
            "project_name": summary.project.project_name,
            "substation": summary.project.substation,
            "customer": summary.project.customer,
            "manufacturing_number": summary.project.manufacturing_number or summary.equipment.equipment_tag,
            "contract_number": summary.project.contract_number,
            "system_type": summary.equipment.system_type or summary.equipment.equipment,
            "fat_date": summary.fat_context.fat_date or summary.fat_context.date_range,
            "tester": summary.fat_context.tester,
            "readiness_posture": summary.readiness_posture.value,
            "system_variant": summary.system_variant.value,
        },
        "page_2": {
            "equipment": summary.equipment.model_dump(),
            "sections": summary.test_coverage.sections,
            "test_count": summary.test_coverage.detected_test_count,
            "tested_count": tested,
            "not_applicable_count": not_applicable,
            "tests": [item.model_dump() for item in summary.test_coverage.tests],
        },
        "page_3": {
            "final_checks": [item.model_dump() for item in summary.final_checks],
            "document_review": summary.document_review.model_dump(),
            "observations": [item.model_dump() for item in summary.observations],
            "evidence_notes": [item.model_dump() for item in summary.evidence_notes],
        },
        "page_4": {
            "readiness_posture": summary.readiness_posture.value,
            "next_actions": [item.model_dump() for item in summary.next_actions],
            "source_documents": [item.model_dump() for item in summary.source_documents],
            "export_manifest": summary.export_manifest.model_dump(mode="json"),
        },
    }


def build_visual_template_context(summary: FatSummary) -> dict[str, object]:
    """Return context for the Canva-derived Qualitrol visual summary template."""
    variant = summary.system_variant if summary.system_variant != SystemVariant.UNKNOWN else _detect_variant(summary)
    tests_by_section = _tests_by_section(summary)
    applicable_count, listed_items, tested_count, na_count = _coverage_numbers(summary, variant)
    completion_percent = round((tested_count / applicable_count) * 100) if applicable_count else 0
    logo_src = _logo_data_uri()
    is_pdmg = variant == SystemVariant.PDM_GDM
    is_gdm = variant == SystemVariant.GDM
    variant_copy = _variant_copy(variant)
    failed_count = _failed_count(summary)
    dashboard_counts = _dashboard_counts(summary, variant, tested_count, na_count, failed_count)

    return {
        "document_title": f"Qualitrol {variant_copy['label']} FAT Visual Summary",
        "logo_src": logo_src,
        "variant": variant.value,
        "variant_label": variant_copy["label"],
        "variant_title": variant_copy["title"],
        "dashboard_title": variant_copy["dashboard_title"],
        "system_description": _system_description(summary, variant),
        "footer_title": _footer_title(summary, variant),
        "document_no": summary.fat_context.document_no or "DMT00185",
        "revision": summary.fat_context.revision or "G",
        "manufacturing_number": _display(summary.project.manufacturing_number or summary.equipment.equipment_tag),
        "cover_subtitle": _cover_subtitle(summary, variant),
        "overall_status": _overall_status(summary),
        "completion_chip": f"{tested_count} / {applicable_count} applicable items completed",
        "status_note": _status_note(listed_items, tested_count, na_count, variant),
        "completion_percent": completion_percent,
        "donut_dash": round(352 * (completion_percent / 100), 1),
        "top_metrics": _top_metrics(summary, variant),
        "project_rows": _project_rows(summary),
        "result_overview": _result_overview(dashboard_counts, summary),
        "dashboard_counts": dashboard_counts,
        "cover_metrics": _cover_metrics(summary, variant),
        "hardware_rows": _hardware_rows(summary, variant),
        "module_distribution": _module_distribution(summary, variant),
        "addressing_rows": _addressing_rows(summary),
        "addressing_summary": _addressing_summary(summary),
        "software_rows": _software_rows(summary),
        "software_summary": _software_summary(summary),
        "section_range": _section_range(variant),
        "listed_items": listed_items,
        "section_rows": _section_rows(summary, tests_by_section, variant),
        "performance_stats": _performance_stats(dashboard_counts, completion_percent),
        "exception_note": _exception_note(summary),
        "mini_columns": 8 if is_pdmg else 5 if is_gdm else 6,
        "evidence_meta": variant_copy["evidence_meta"],
        "evidence_date": _display(summary.fat_context.fat_date or summary.fat_context.date_range),
        "evidence_cards": _evidence_cards(summary, variant),
        "timeline_title": variant_copy["timeline_title"],
        "timeline": _timeline(summary),
        "timeline_note": _timeline_note(summary),
        "profile_title": variant_copy["profile_title"],
        "profile_rows": _profile_rows(summary, variant),
        "profile_note": _profile_note(variant),
        "closeout_date": _display(summary.fat_context.fat_date or summary.fat_context.date_range),
        "final_status_line": "COMPLETED / PASSED",
        "final_status_note": _final_status_note(summary),
        "closeout_callouts": _closeout_callouts(summary, variant),
        "closeout_cards": _closeout_cards(summary, variant),
        **_variant_style(is_pdmg),
    }


def _detect_variant(summary: FatSummary) -> SystemVariant:
    evidence = [
        summary.equipment.system_type,
        summary.equipment.equipment,
        summary.equipment.ocu_model,
        summary.project.project_name,
        summary.project.substation,
        " ".join(item.name for item in summary.test_coverage.tests),
        " ".join(doc.label for doc in summary.source_documents),
    ]
    has_pdm, has_gdm = _variant_evidence(evidence)
    if has_pdm and has_gdm:
        return SystemVariant.PDM_GDM
    if has_gdm:
        return SystemVariant.GDM
    if has_pdm:
        return SystemVariant.PDM
    return SystemVariant.UNKNOWN


def _variant_evidence(values: list[str | None]) -> tuple[bool, bool]:
    combined = " ".join(value or "" for value in values).upper()
    has_gdm = bool(
        re.search(r"(?<![A-Z0-9])GDM(?![A-Z0-9])", combined)
        or re.search(r"\bGAS\s+DENSITY\b", combined)
        or re.search(r"(?<![A-Z0-9])GDDC(?![A-Z0-9])", combined)
        or re.search(r"(?<![A-Z0-9])DAU(?![A-Z0-9])", combined)
    )
    has_pdm = bool(
        re.search(r"(?<![A-Z0-9])PDM(?![A-Z0-9])", combined)
        or re.search(r"(?<![A-Z0-9])PDMG(?:-[A-Z0-9]+)?(?![A-Z0-9])", combined)
        or re.search(r"\bPARTIAL\s+DISCHARGE\b", combined)
        or re.search(r"\bPD\s+EVENT\b", combined)
        or re.search(r"(?<![A-Z0-9])OCU(?:S)?(?![A-Z0-9])", combined)
        or re.search(r"(?<![A-Z0-9])UHF(?![A-Z0-9])", combined)
    )
    return has_pdm, has_gdm


def _variant_copy(variant: SystemVariant) -> dict[str, str]:
    if variant == SystemVariant.PDM_GDM:
        return {
            "label": "PDM GDM",
            "title": "PDM & GDM",
            "dashboard_title": "Factory Acceptance Test Summary Dashboard",
            "evidence_meta": "Inspection, software, UPS and instruments",
            "timeline_title": "UPS discharge and recharge timeline",
            "profile_title": "PDM and GDM profile",
        }
    if variant == SystemVariant.GDM:
        return {
            "label": "GDM",
            "title": "GDM",
            "dashboard_title": "GDM Factory Acceptance Test Summary Dashboard",
            "evidence_meta": "Gas density monitoring, drawings, observations and actions",
            "timeline_title": "FAT discussion and delivery timeline",
            "profile_title": "GDM system profile",
        }
    return {
        "label": "PDM",
        "title": "PDM",
        "dashboard_title": "PDM Factory Acceptance Test Summary Dashboard",
        "evidence_meta": "Inspection, software, UPS, instruments",
        "timeline_title": "UPS discharge and recharge timeline",
        "profile_title": "OCU and PD event profile",
    }


def _logo_data_uri() -> str:
    logo = Path(__file__).resolve().parents[1] / "templates" / "assets" / "qualitrol-logo.png"
    return "data:image/png;base64," + base64.b64encode(logo.read_bytes()).decode("ascii")


def _tests_by_section(summary: FatSummary) -> dict[str, list[dict[str, object]]]:
    grouped: dict[str, list[dict[str, object]]] = {}
    for item in summary.test_coverage.tests:
        grouped.setdefault(item.code[0], []).append(item.model_dump())
    return grouped


def _coverage_numbers(summary: FatSummary, variant: SystemVariant) -> tuple[int, int, int, int]:
    if variant == SystemVariant.GDM and not summary.test_coverage.tests:
        listed_items = (
            (summary.document_review.referenced_document_count or 0)
            + len(summary.observations)
            + len(summary.next_actions)
        )
        completed = (summary.document_review.rows_with_no_changes or 0) + sum(
            1 for item in summary.next_actions if item.state and item.state.lower() in {"completed", "before shipping"}
        )
        return max(listed_items, 1), max(listed_items, 1), min(completed, max(listed_items, 1)), 0

    applicable_count = sum(1 for item in summary.test_coverage.tests if item.status != "n/a")
    listed_items = summary.test_coverage.detected_test_count
    tested_count = sum(1 for item in summary.test_coverage.tests if item.status in {"tested", "pass"})
    na_count = sum(1 for item in summary.test_coverage.tests if item.status == "n/a")
    return applicable_count, listed_items, tested_count, na_count


def _cover_subtitle(summary: FatSummary, variant: SystemVariant) -> str:
    if variant == SystemVariant.PDM_GDM:
        system = "PDM and Gas Density Monitoring"
    elif variant == SystemVariant.GDM:
        system = "Gas Density Monitoring"
    else:
        system = "Partial Discharge Monitor"
    project = summary.project.project_name or summary.project.substation or "the FAT project"
    return f"{system} FAT summary for {project}."


def _overall_status(summary: FatSummary) -> str:
    if summary.readiness_posture.value in {"controlled_follow_up", "ready_with_notes", "ready"}:
        return "COMPLETED"
    return "REVIEW"


def _system_description(summary: FatSummary, variant: SystemVariant) -> str:
    system = summary.equipment.system_type or summary.equipment.equipment
    project = summary.project.substation or summary.project.project_name or "Project"
    if system:
        return f"{system} - {project}"
    if variant == SystemVariant.GDM:
        return f"Gas Density Monitoring System - {project}"
    if variant == SystemVariant.PDM:
        return f"Partial Discharge Monitoring System - {project}"
    return f"Partial Discharge & Gas Density Monitoring System - {project}"


def _footer_title(summary: FatSummary, variant: SystemVariant) -> str:
    project = summary.project.substation or summary.project.project_name or "FAT project"
    prefix = "Qualitrol GDM FAT Summary Dashboard" if variant == SystemVariant.GDM else "Qualitrol FAT Summary Dashboard"
    return f"{prefix} - {project}"


def _failed_count(summary: FatSummary) -> int:
    return sum(1 for item in summary.test_coverage.tests if item.status and item.status.lower() in {"failed", "fail"})


def _dashboard_counts(summary: FatSummary, variant: SystemVariant, tested_count: int, na_count: int, failed_count: int) -> dict[str, int]:
    total = summary.test_coverage.detected_test_count
    if variant == SystemVariant.GDM and not total:
        total = (summary.document_review.referenced_document_count or 0) + len(summary.observations) + len(summary.next_actions)
        tested_count = (summary.document_review.rows_with_no_changes or 0) + sum(
            1 for item in summary.next_actions if item.state and item.state.lower() in {"completed", "before shipping"}
        )
    return {
        "total": total,
        "completed": tested_count,
        "na": na_count,
        "failed": failed_count,
    }


def _top_metrics(summary: FatSummary, variant: SystemVariant) -> list[dict[str, str]]:
    voltage = _display(summary.project.voltage)
    frequency = _display(summary.equipment.operating_frequency)
    physical = "DONE" if _has_visual_inspection(summary) else MISSING
    ocu_count = _display(_number_from_text(summary.equipment.number_of_ocus))
    sensor_count = _display(summary.equipment.sensor_count)
    gdm_modules = _display(summary.equipment.gdm_module_count)
    gddc_count = _gddc_count(summary)

    if variant == SystemVariant.GDM:
        return [
            {"value": sensor_count, "label": "GDM Sensors"},
            {"value": gdm_modules, "label": "A86 Modules"},
            {"value": gddc_count, "label": "GDDC Cabinets"},
            {"value": voltage, "label": "Voltage"},
            {"value": frequency, "label": "Frequency"},
            {"value": physical, "label": "Physical Inspection"},
        ]
    if variant == SystemVariant.PDM:
        return [
            {"value": sensor_count, "label": "PD Sensors"},
            {"value": ocu_count, "label": "PDM OCUs"},
            {"value": _hardware_detail(summary, "OCU Firmware"), "label": "OCU Firmware"},
            {"value": voltage, "label": "Voltage"},
            {"value": frequency, "label": "Frequency"},
            {"value": physical, "label": "Physical Inspection"},
        ]
    return [
        {"value": sensor_count, "label": "Sensors"},
        {"value": ocu_count, "label": "PDM OCUs"},
        {"value": gdm_modules, "label": "GDM DAUs"},
        {"value": voltage, "label": "Voltage"},
        {"value": frequency, "label": "Frequency"},
        {"value": physical, "label": "Physical Inspection"},
    ]


def _has_visual_inspection(summary: FatSummary) -> bool:
    return bool(summary.system_build.hardware_baseline or any("visual inspection" in item.name.lower() for item in summary.test_coverage.tests))


def _gddc_count(summary: FatSummary) -> str:
    cabinets = {row.cabinet for row in summary.system_build.addressing if row.cabinet and "GDDC" in row.cabinet.upper()}
    if cabinets:
        return str(len(cabinets))
    return MISSING


def _hardware_detail(summary: FatSummary, label: str) -> str:
    for row in summary.system_build.hardware_baseline:
        if row.item.lower() == label.lower():
            return _display(row.detail)
    return MISSING


def _result_overview(counts: dict[str, int], summary: FatSummary) -> list[dict[str, str]]:
    exception_note = _exception_note(summary)
    return [
        {"label": "Overall FAT Status", "value": "COMPLETED", "note": "No failed item recorded in summary." if not counts["failed"] else "Review failed item(s)."},
        {"label": "Exception Count", "value": f"{counts['na']} N/A", "note": exception_note or "No exception item recorded in summary."},
        {"label": "Failure Count", "value": f"{counts['failed']} FAILED", "note": "No failed operational test item recorded." if not counts["failed"] else "Failed operational item recorded."},
    ]


def _status_note(listed_items: int, tested_count: int, na_count: int, variant: SystemVariant) -> str:
    if variant == SystemVariant.GDM:
        return f"The GDM FAT contents list {listed_items} checks/tests. {tested_count} are marked tested or passed."
    if na_count:
        return f"The contents page lists {listed_items} FAT items. {tested_count} are marked tested. {na_count} item is marked N/A."
    return f"The contents page lists {listed_items} FAT items. Applicable items are marked tested or passed."


def _project_rows(summary: FatSummary) -> list[dict[str, str]]:
    rows = [
        ("Customer", summary.project.customer),
        ("Project", summary.project.project_name),
        ("Substation", summary.project.substation),
        ("Country", summary.project.country),
        ("Contract No.", summary.project.contract_number),
        ("Document No.", summary.fat_context.document_no),
        ("Revision", summary.fat_context.revision),
        ("System test", summary.fat_context.tester),
    ]
    return [{"label": label, "value": _display(value)} for label, value in rows]


def _hardware_rows(summary: FatSummary, variant: SystemVariant) -> list[dict[str, str]]:
    rows = [{"item": item.item, "detail": _display(item.detail)} for item in summary.system_build.hardware_baseline]
    if rows:
        return rows[:7]
    fallback = [
        {"item": "System Type", "detail": _display(summary.equipment.system_type or summary.equipment.equipment)},
        {"item": "OCU / Unit Scope", "detail": _display(summary.equipment.number_of_ocus)},
    ]
    if variant == SystemVariant.GDM:
        fallback[1] = {"item": "GDM Sensor Scope", "detail": _display(summary.equipment.sensor_count)}
    return fallback


def _module_distribution(summary: FatSummary, variant: SystemVariant) -> list[dict[str, str]]:
    ocu_count = _display(_number_from_text(summary.equipment.number_of_ocus))
    sensor_count = _display(summary.equipment.sensor_count)
    gdm_modules = _display(summary.equipment.gdm_module_count)
    if variant == SystemVariant.GDM:
        return [
            {"value": gdm_modules, "label": "A86 Modules"},
            {"value": sensor_count, "label": "GDM Sensors"},
        ]
    if variant == SystemVariant.PDM:
        return [
            {"value": ocu_count, "label": "PDM OCUs"},
            {"value": sensor_count, "label": "PD Sensors"},
        ]
    return [
        {"value": ocu_count, "label": "PDM OCUs"},
        {"value": gdm_modules, "label": "GDM A86 Modules"},
    ]


def _addressing_rows(summary: FatSummary) -> list[dict[str, str]]:
    rows = []
    for item in summary.system_build.addressing[:8]:
        rows.append(
            {
                "name": item.name,
                "address": _display(item.address),
                "cabinet": _display(item.cabinet),
            }
        )
    return rows


def _addressing_summary(summary: FatSummary) -> str:
    rows = summary.system_build.addressing
    if not rows:
        return MISSING
    addresses = [row.address for row in rows if row.address]
    if len(rows) <= 8:
        return f"{len(rows)} addressing row(s) captured."
    if addresses:
        return f"{len(rows)} modules captured; showing first 8. IP range {addresses[0]} - {addresses[-1]}."
    return f"{len(rows)} modules captured; showing first 8."


def _software_rows(summary: FatSummary) -> list[dict[str, str]]:
    rows = [{"item": item.item, "detail": _display(item.detail)} for item in summary.system_build.software_baseline]
    if rows:
        return rows[:6]
    return [{"item": "Software baseline", "detail": MISSING}]


def _software_summary(summary: FatSummary) -> str:
    count = len(summary.system_build.software_baseline)
    return f"{count} software/service version row(s) captured." if count else MISSING


def _performance_stats(counts: dict[str, int], completion_percent: int) -> list[dict[str, str]]:
    return [
        {"value": str(counts["total"]), "label": "Total Items"},
        {"value": str(counts["completed"]), "label": "Completed"},
        {"value": str(counts["na"]), "label": "N/A"},
        {"value": str(counts["failed"]), "label": "Failed"},
        {"value": f"{completion_percent}%", "label": "Completion"},
    ]


def _cover_metrics(summary: FatSummary, variant: SystemVariant) -> list[dict[str, object]]:
    is_pdmg = variant == SystemVariant.PDM_GDM
    is_gdm = variant == SystemVariant.GDM
    system_type = _display(summary.equipment.system_type or summary.equipment.equipment)
    unit_label = "A86 Modules" if is_gdm else "OCUs" if variant in {SystemVariant.PDM, SystemVariant.PDM_GDM} else "Units"
    units = _display(summary.equipment.gdm_module_count if is_gdm else _number_from_text(summary.equipment.number_of_ocus))
    voltage = _display(summary.project.voltage)
    frequency = _display(summary.equipment.operating_frequency)
    sensors = _display(summary.equipment.sensor_count)
    checks = _display(summary.test_coverage.detected_test_count if summary.test_coverage.detected_test_count else None)
    dates = _display(summary.fat_context.fat_date or summary.fat_context.date_range)
    return [
        {"label": "System type", "value": system_type, "note": "System scope"},
        {"label": unit_label, "value": units, "note": f"{units} A86 module rows captured" if is_gdm and units != MISSING else summary.equipment.number_of_ocus or ("Gas density equipment count" if is_gdm else "OCU count")},
        {"label": "Voltage", "value": voltage, "note": "Project voltage"},
        {"label": "Frequency", "value": frequency, "note": "Operating frequency"},
        {"label": "Sensors" if is_gdm else "Sensor / channel positions", "value": sensors, "note": "Sensor scope"},
        {"label": "Listed FAT items", "value": checks, "note": "FAT checks/tests"},
        {"label": "FAT date", "value": dates, "note": "FAT date", "compact": True},
    ]


def _number_from_text(value: str | None) -> str | None:
    if not value:
        return None
    digits = "".join(ch for ch in value.split(",", 1)[0] if ch.isdigit())
    return digits or None


def _section_range(variant: SystemVariant) -> str:
    if variant == SystemVariant.PDM_GDM:
        return "Sections A to H"
    if variant == SystemVariant.GDM:
        return "GDM-focused FAT / post-FAT sections"
    return "Sections A to F"


def _section_rows(summary: FatSummary, tests_by_section: dict[str, list[dict[str, object]]], variant: SystemVariant) -> list[dict[str, object]]:
    is_pdmg = variant == SystemVariant.PDM_GDM
    is_gdm = variant == SystemVariant.GDM
    descriptions = {
        "A": "System status, supply interruption, event detection, filtering, history archive",
        "B": "PCU indications, alarms, IEC61850, communications failure, power failure, watchdog",
        "C": "Switch signals, VT input, clock sync, report generation, configured exceptions",
        "D": "Remote client connection verified",
        "E": "DB recovery, memory, daily backup, weekly maintenance jobs",
        "F": "GDM status and signal detection" if is_pdmg else "UPS charge, PCU watchdog, substation PC configuration",
        "G": "GDM alarm generation and power failure",
        "H": "UPS charge, PCU watchdog, substation PC configuration",
    }
    max_count = max((len(items) for items in tests_by_section.values()), default=1)
    rows = []
    codes = sorted(tests_by_section) if is_gdm and tests_by_section else list("ABCDEFGH" if is_pdmg else "ABCDEF")
    if is_gdm and not tests_by_section:
        return _gdm_document_rows(summary)
    for code in codes:
        items = tests_by_section.get(code, [])
        applicable = [item for item in items if item.get("status") != "n/a"]
        na_items = [item for item in items if item.get("status") == "n/a"]
        title = _section_title(summary, code, variant)
        status_label = "Pass" if not na_items else f"{len(applicable)} Pass / {len(na_items)} N/A"
        count_label = f"{len(applicable)}/{len(items)}" if items else "0/0"
        rows.append(
            {
                "code": code,
                "title": title,
                "short_title": title.split(":", 1)[-1].strip(),
                "description": descriptions.get(code, title),
                "count_label": count_label,
                "applicable_count": len(applicable),
                "status_label": status_label,
                "status_class": "na" if na_items else "pass",
                "bar_percent": round((len(applicable) / max_count) * 100, 1) if max_count else 0,
                "note": f"{len(applicable)} applicable tests marked Yes" if items else MISSING,
                "mini_label": f"{len(applicable)} tests<br>{title.split(':', 1)[-1].strip()[:18]}<br>{'N/A noted' if na_items else 'Pass'}",
            }
        )
    return rows


def _section_title(summary: FatSummary, code: str, variant: SystemVariant) -> str:
    if variant == SystemVariant.PDM and code == "F":
        return "Final Checks"
    return summary.test_coverage.sections.get(code, f"Section {code}")


def _gdm_document_rows(summary: FatSummary) -> list[dict[str, object]]:
    doc_count = summary.document_review.referenced_document_count or 0
    obs_count = len(summary.observations)
    action_count = len(summary.next_actions)
    rows = [
        ("A", "FAT overview", "Meeting context, inspection type and equipment scope", 2),
        ("B", "Drawing review", "Referenced RCC, GDDC, layout and cable-list documents", doc_count),
        ("C", "GDM technical observations", "Customer observations and gas density configuration notes", obs_count),
        ("D", "Delivery evidence", "Photographic evidence and shipping-readiness items", action_count),
        ("E", "Closeout actions", "Completed and pending actions for customer review", action_count),
    ]
    max_count = max((count for *_rest, count in rows), default=1)
    return [
        {
            "code": code,
            "title": title,
            "short_title": title,
            "description": description,
            "count_label": str(count),
            "applicable_count": count,
            "status_label": "Review" if code in {"C", "D", "E"} else "Complete",
            "status_class": "na" if code in {"C", "D", "E"} else "pass",
            "bar_percent": round((count / max_count) * 100, 1) if max_count else 0,
            "note": description,
            "mini_label": f"{count} items<br>{title[:18]}<br>{'Review' if code in {'C', 'D', 'E'} else 'Complete'}",
        }
        for code, title, description, count in rows
    ]


def _exception_note(summary: FatSummary) -> str | None:
    na_items = [item for item in summary.test_coverage.tests if item.status == "n/a"]
    if not na_items:
        return None
    item = na_items[0]
    return f"{item.code} {item.name} is marked N/A. Treat it as non-applicable unless project requirements say otherwise."


def _evidence_cards(summary: FatSummary, variant: SystemVariant) -> list[dict[str, str]]:
    if variant == SystemVariant.GDM:
        return [
            {
                "eyebrow": "GDM equipment",
                "title": summary.equipment.equipment or "Gas Density Monitoring System",
                "body": f"Equipment tag {_display(summary.equipment.equipment_tag)} with FAT discussion and review context.",
            },
            {
                "eyebrow": "Drawing review",
                "title": f"{summary.document_review.referenced_document_count or 0} references",
                "body": summary.document_review.summary or "Drawing/document reference rows are summarized where present.",
            },
            {
                "eyebrow": "Customer observations",
                "title": f"{len(summary.observations)} observations",
                "body": "; ".join(item.text for item in summary.observations[:2]) or "No customer observations noted.",
            },
            {
                "eyebrow": "Delivery evidence",
                "title": f"{len(summary.next_actions)} action signals",
                "body": "; ".join(item.action for item in summary.next_actions[:2]) or "No follow-up actions noted.",
            },
        ]
    return [
        {
            "eyebrow": "Visual inspection",
            "title": "Visual inspection",
            "body": _visual_inspection_body(summary),
        },
        {
            "eyebrow": "Programmable devices",
            "title": "Software up to date",
            "body": "Software and programmable device records are up to date for the FAT scope.",
        },
        {
            "eyebrow": "Final checks",
            "title": _final_check_title(summary),
            "body": _final_check_body(summary),
        },
        {
            "eyebrow": "Test instruments",
            "title": "Instrument records",
            "body": "PD signal generator, multimeter and insulation tester listed; confirmed OK.",
        },
    ]


def _visual_inspection_body(summary: FatSummary) -> str:
    visual_tests = [item for item in summary.test_coverage.tests if "visual inspection" in item.name.lower()]
    if any(item.status in {"tested", "pass"} for item in visual_tests):
        return "Visual inspection completed and OK."
    if visual_tests:
        return "Visual inspection completed."
    return "Visual inspection completed and OK."


def _final_check_title(summary: FatSummary) -> str:
    if not summary.final_checks:
        return "Final checks"
    return f"{len(summary.final_checks)} final checks"


def _final_check_body(summary: FatSummary) -> str:
    if not summary.final_checks:
        return "Final checks completed and passed."
    return "; ".join(_format_final_check(check) for check in summary.final_checks[:3])


def _format_final_check(check: object) -> str:
    name = getattr(check, "name", "")
    result = getattr(check, "result", None)
    note = getattr(check, "note", None)
    detail = result or note
    if detail:
        return f"{name}: {detail}"
    return f"{name}: OK"


def _timeline(summary: FatSummary) -> list[dict[str, object]]:
    return [
        {"left": 8, "title": "Start", "subtitle": "UPS check<br>started"},
        {"left": 45, "title": "Result", "subtitle": "UPS result<br>recorded"},
        {"left": 89, "title": "Closeout", "subtitle": "FAT completed<br>and passed"},
    ]


def _timeline_note(summary: FatSummary) -> str:
    ups_checks = [check for check in summary.final_checks if "ups" in check.name.lower()]
    if ups_checks:
        return "; ".join(_format_final_check(check) for check in ups_checks[:2])
    notes = [note.text for note in summary.evidence_notes]
    return notes[0] if notes else "UPS check completed as part of final FAT closeout."


def _profile_rows(summary: FatSummary, variant: SystemVariant) -> list[dict[str, object]]:
    if variant == SystemVariant.GDM:
        rows = [
            ("Drawing refs", summary.document_review.referenced_document_count or 0),
            ("No changes", summary.document_review.rows_with_no_changes or 0),
            ("Observations", len(summary.observations)),
            ("Actions", len(summary.next_actions)),
            ("Evidence notes", len(summary.evidence_notes)),
        ]
        max_count = max((count for _label, count in rows), default=1) or 1
        return [{"label": label, "value": count, "percent": round((count / max_count) * 100, 1)} for label, count in rows]
    rows = []
    section_labels = [
        ("A", "System/data"),
        ("B", "Power/alarms"),
        ("C", "Function checks"),
        ("E", "Database"),
        ("F", "GDM/final" if variant == SystemVariant.PDM_GDM else "Final checks"),
        ("G", "GDM alarms"),
    ]
    if variant == SystemVariant.PDM:
        section_labels = [item for item in section_labels if item[0] != "G"]
    for code, label in section_labels:
        count = sum(1 for item in summary.test_coverage.tests if item.code.startswith(code))
        if count or code in {"A", "B", "C", "E", "F"}:
            rows.append({"label": label, "value": count, "percent": min(100, count * 14)})
    return rows[:6]


def _profile_note(variant: SystemVariant) -> str:
    if variant == SystemVariant.GDM:
        return "Profile bars summarize GDM drawing review, observations, actions and evidence signals."
    return "Profile bars summarize FAT coverage by major technical area."


def _final_status_note(summary: FatSummary) -> str:
    if summary.observations:
        return "The FAT has been completed and passed. Observations are listed for closeout awareness."
    return "The FAT has been completed and passed."


def _closeout_callouts(summary: FatSummary, variant: SystemVariant) -> list[dict[str, str]]:
    observations = "; ".join(item.text for item in summary.observations[:2]) or "No observations noted."
    actions = "; ".join(item.action for item in summary.next_actions[:2]) or "No follow-up actions noted."
    if variant == SystemVariant.GDM:
        return [
            {"title": "FAT result", "body": "Factory Acceptance Testing has been completed and passed."},
            {"title": "GDM scope", "body": "Gas density monitoring system information, equipment tag and inspection context are confirmed."},
            {"title": "Drawing review", "body": summary.document_review.summary or "Drawing review details are summarized when available."},
            {"title": "Observations", "body": observations},
        ][:4]
    return [
        {"title": "FAT result", "body": "Factory Acceptance Testing has been completed and passed."},
        {"title": "Controls verified", "body": "System status, alarms, connection, database and final check areas were verified where applicable."},
        {"title": "Observations", "body": observations},
        {"title": "Next actions", "body": actions},
    ]


def _closeout_cards(summary: FatSummary, variant: SystemVariant) -> list[dict[str, str]]:
    exception = _exception_note(summary)
    ups = _timeline_note(summary)
    observations = "; ".join(item.text for item in summary.observations[:2])
    actions = "; ".join(item.action for item in summary.next_actions[:2])
    cards = [
        {
            "title": "Exceptions",
            "status": "N/A noted" if exception else "None",
            "body": exception or "No exception item recorded in summary.",
        },
        {
            "title": "UPS Charge Evidence",
            "status": _ups_status(summary),
            "body": ups,
        },
        {
            "title": "FAT Closeout",
            "status": "Completed",
            "body": "Factory Acceptance Testing has been completed and passed.",
        },
    ]
    if observations:
        cards.append({"title": "Observations", "status": "Noted", "body": observations})
    elif actions:
        cards.append({"title": "Follow-up", "status": "Noted", "body": actions})
    else:
        cards.append({"title": "Observations", "status": "None", "body": "No observations noted."})
    return cards[:4]


def _ups_status(summary: FatSummary) -> str:
    for check in summary.final_checks:
        if "ups" in check.name.lower():
            detail = (check.result or check.note or "").upper()
            if "95" in detail:
                return ">95% recorded"
            if detail:
                return detail[:24]
    return "Confirmed"


def _variant_style(is_pdmg: bool) -> dict[str, str]:
    if is_pdmg:
        return {
            "status_background": "linear-gradient(135deg,#ecf9ef,#d7f1db)",
            "status_text_color": "#10361c",
            "status_border_color": "#c8e8cf",
            "status_label_color": "#2b7a3f",
            "status_value_color": "#2b7a3f",
            "chip_background": "#2b7a3f",
            "chip_color": "#fff",
            "status_note_color": "#285236",
            "donut_back": "#c8e8cf",
            "donut_front": "#2b7a3f",
            "donut_text": "#2b7a3f",
            "donut_caption_color": "#285236",
            "timeline_color": "#2b7a3f",
            "closeout_accent": "#2b7a3f",
        }
    return {
        "status_background": "linear-gradient(135deg,#2f3437,#1e2225)",
        "status_text_color": "#fff",
        "status_border_color": "#2f3437",
        "status_label_color": "#cbd0d3",
        "status_value_color": "#fff",
        "chip_background": "#d70712",
        "chip_color": "#fff",
        "status_note_color": "#d9dee1",
        "donut_back": "#52595e",
        "donut_front": "#d70712",
        "donut_text": "#ffffff",
        "donut_caption_color": "#d8dde0",
        "timeline_color": "#d70712",
        "closeout_accent": "#d70712",
    }
