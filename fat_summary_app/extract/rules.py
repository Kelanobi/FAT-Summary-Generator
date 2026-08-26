from __future__ import annotations

import re
from pathlib import Path

from fat_summary_app.extract.pdf import PdfDocument, read_pdf
from fat_summary_app.extract.text_utils import clean_lines, first_match, value_after_label
from fat_summary_app.models import (
    ActionItem,
    AddressingRow,
    DocumentReview,
    Equipment,
    EvidenceNote,
    FatContext,
    FatSummary,
    FinalCheck,
    Observation,
    Project,
    SourceDocument,
    SystemBuild,
    SystemBuildItem,
    TestCoverage,
    TestItem,
)
from fat_summary_app.models.report import ReadinessPosture, SystemVariant


SECTION_NAMES = {
    "A": "System status and data recording",
    "B": "Power control and alarms",
    "C": "Specific function tests",
    "D": "Remote Client Connection",
    "E": "Database Checks",
    "F": "GDM: System status and data recording",
    "G": "GDM: Power control and alarms",
    "H": "Final Checks",
}


def extract_fat_summary(paths: list[str | Path], system_variant: SystemVariant | str | None = None) -> FatSummary:
    docs = [read_pdf(path) for path in paths]
    summary = FatSummary(source_documents=[_source_document(doc) for doc in docs])

    for doc in docs:
        text = doc.text
        if "Factory Acceptance Test Record" in text:
            _merge_after_fat(summary, doc)
        if "MINUTES OF MEETING" in text or "Post FAT discussion" in text:
            _merge_post_fat(summary, doc)

    summary.readiness_posture = _infer_readiness(summary)
    forced_variant = _coerce_system_variant(system_variant)
    summary.system_variant = forced_variant or detect_system_variant(summary)
    return summary


def _coerce_system_variant(system_variant: SystemVariant | str | None) -> SystemVariant | None:
    if system_variant is None:
        return None
    if isinstance(system_variant, SystemVariant):
        return None if system_variant == SystemVariant.UNKNOWN else system_variant
    normalized = system_variant.strip().lower()
    if normalized in {"", "auto", "unknown"}:
        return None
    if normalized in {"pdm/gdm", "pdm-gdm", "pdm_gdm", "pdmg"}:
        return SystemVariant.PDM_GDM
    return SystemVariant(normalized)


def detect_system_variant(summary: FatSummary) -> SystemVariant:
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


def _source_document(doc: PdfDocument) -> SourceDocument:
    return SourceDocument(
        label=doc.path.stem,
        path=str(doc.path),
        pages=doc.page_count,
        sha256=doc.sha256,
    )


def _merge_after_fat(summary: FatSummary, doc: PdfDocument) -> None:
    page_two = _contract_information_text(doc)
    summary.project = Project(
        project_name=value_after_label(page_two, "Project"),
        substation=value_after_label(page_two, "Substation"),
        customer=value_after_label(page_two, "Customer"),
        country=value_after_label(page_two, "Country"),
        voltage=_extract_voltage(page_two),
        contract_number=value_after_label(page_two, "Contract number"),
        manufacturing_number=value_after_label(page_two, "Manufacturing number"),
    )
    summary.equipment = Equipment(
        system_type=value_after_label(page_two, "Type"),
        equipment=value_after_label(page_two, "GDM Sensors"),
        ocu_model=value_after_label(page_two, "OCU model"),
        operating_frequency=value_after_label(page_two, "Operating frequency"),
        number_of_ocus=value_after_label(page_two, "Number of OCUs"),
        sensor_count=_extract_sensor_count(page_two),
    )
    summary.fat_context = FatContext(
        document_no=value_after_label(page_two, "Document No.") or first_match(page_two, r"Document No\.?\s*\n?\s*([A-Z0-9]+)"),
        revision=value_after_label(page_two, "Revision:") or first_match(page_two, r"Revision:?\s*\n?\s*([A-Z])"),
        fat_date=_extract_first_date(page_two) or _extract_first_date(doc.text),
        tester=first_match(page_two, r"System test\s*\n([^\n]+)") or first_match(doc.text, r"Qualitrol:\s*([^\n]+)"),
        project_owner=first_match(page_two, r"Project planning\s*\n([^\n]+)"),
    )
    summary.test_coverage = _extract_test_coverage(doc)
    summary.system_build = _extract_system_build(doc, summary)
    summary.final_checks.extend(_extract_final_checks(doc))
    summary.evidence_notes.extend(_extract_after_fat_evidence(doc))


def _contract_information_text(doc: PdfDocument) -> str:
    for page in doc.pages[:5]:
        if "Contract Information" in page.text and "System Information" in page.text:
            return page.text
    return "\n".join(page.text for page in doc.pages[:2]) if doc.pages else doc.text


def _extract_voltage(text: str) -> str | None:
    value = value_after_label(text, "Voltage")
    if not value:
        return None
    match = re.search(r"\b\d+(?:\.\d+)?\s*(?:KVAC|KVDC|VAC|VDC|KV|V)\b", value, re.IGNORECASE)
    return match.group(0).replace(" ", "") if match else None


def _extract_first_date(text: str) -> str | None:
    return first_match(text, r"Date\s*\n(\d{1,2}/\d{1,2}/\d{4})") or _first_date_anywhere(text)


def _first_date_anywhere(text: str) -> str | None:
    match = re.search(r"\b(\d{1,2}/\d{1,2}/\d{4})\b", text)
    return match.group(1) if match else None


def _extract_test_coverage(doc: PdfDocument) -> TestCoverage:
    sections = SECTION_NAMES | _extract_contents_sections(doc)
    contents_items = _extract_contents_items(doc)
    contents_status = {code: item["status"] for code, item in contents_items.items() if item.get("status")}
    seen: set[str] = set()
    tests: list[TestItem] = []
    for code, item in contents_items.items():
        tests.append(TestItem(code=code, name=item["name"], status=item.get("status"), page=_find_test_page(doc, code, item["name"])))
        seen.add(code)
    for page in doc.pages:
        for raw_code, name in re.findall(r"\b(?:Test|Check)\s+([A-H0-9Il]{1,4})\s*:\s*([^\n]+)", page.text):
            code = _normalize_test_code(raw_code)
            if not code:
                continue
            if code in seen:
                continue
            seen.add(code)
            status = contents_status.get(code)
            tests.append(TestItem(code=code, name=name.strip(), status=status, page=page.number))
    return TestCoverage(sections=sections, tests=tests, detected_test_count=len(tests))


def _extract_contents_sections(doc: PdfDocument) -> dict[str, str]:
    sections: dict[str, str] = {}
    for page in doc.pages:
        if "Contents" not in page.text:
            continue
        lines = clean_lines(page.text)
        for index, line in enumerate(lines):
            match = re.match(r"Section\s+([A-H])\b", line, re.IGNORECASE)
            if not match:
                continue
            title_parts: list[str] = []
            for next_line in lines[index + 1 : index + 5]:
                if re.fullmatch(r"Tested|Yes|No", next_line, re.IGNORECASE):
                    break
                if re.match(r"(?:Test|Check)\s+", next_line, re.IGNORECASE):
                    break
                title_parts.append(next_line)
            if title_parts:
                sections[match.group(1).upper()] = " ".join(title_parts)
    return sections


def _find_test_page(doc: PdfDocument, code: str, name: str) -> int | None:
    code_pattern = re.compile(rf"\b(?:Test|Check)\s+{re.escape(code)}\b", re.IGNORECASE)
    relaxed_name = re.sub(r"\s+", r"\\s+", re.escape(name[:25]))
    name_pattern = re.compile(relaxed_name, re.IGNORECASE) if relaxed_name else None
    for page in doc.pages:
        normalized = _normalize_ocr_codes(page.text)
        if code_pattern.search(normalized):
            return page.number
        if name_pattern and name_pattern.search(page.text):
            return page.number
    return None


def _extract_sensor_count(text: str) -> int | None:
    match = re.search(r"\b(?:for\s+)?(\d{1,4})\s+Sensors?\b", text, re.IGNORECASE)
    return int(match.group(1)) if match else None


def _extract_system_build(doc: PdfDocument, summary: FatSummary) -> SystemBuild:
    text = doc.text
    addressing = _extract_addressing_rows(text)
    if addressing:
        summary.equipment.gdm_module_count = len(addressing)

    hardware = _extract_hardware_baseline(text, summary)
    software = _extract_software_baseline(text)
    return SystemBuild(hardware_baseline=hardware, software_baseline=software, addressing=addressing)


def _extract_hardware_baseline(text: str, summary: FatSummary) -> list[SystemBuildItem]:
    rows: list[SystemBuildItem] = []
    candidates = [
        ("System Type", summary.equipment.system_type or summary.equipment.equipment),
        ("OCU Model", summary.equipment.ocu_model),
        ("OCU Firmware", _first_match_any(text, [r"\bOCU\s+01\s*\nOCU\s+01\s*\n[^\n]+\n[^\n]+\n([0-9][^\n]+)"])),
        ("RCC", _first_match_any(text, [r"\bRCC1\s*\n([^\n]+)"])),
        ("RDC/GDDC", _first_match_any(text, [r"\bPDM/GDM RDC\s*\n([^\n]+)", r"\bGDDC1\s*\n([^\n]+)"])),
        ("PCU", _first_match_any(text, [r"PCU \(Power Control Unit\)\s*\n([^\n]+)"])),
        ("UPS", _first_match_any(text, [r"\bUPS\s*\n([^\n]+)"])),
        ("Server", _first_match_any(text, [r"\bServer\s*\n([^\n]+)"])),
        ("Ethernet Switch", _first_match_any(text, [r"Ethernet Switch 1\s*\n([^\n]+)", r"Ethernet Switch\s*\n([^\n]+)"])),
        ("Sync Interface", _first_match_any(text, [r"Sync Interface\s*\n([^\n]+)"])),
        ("Sync Driver", _first_match_any(text, [r"Sync Driver\s*\n([^\n]+)"])),
    ]
    for item, detail in candidates:
        if detail:
            rows.append(SystemBuildItem(item=item, detail=_clean_cell(detail)))
    return rows


def _extract_software_baseline(text: str) -> list[SystemBuildItem]:
    software_patterns = [
        ("SmartPDM Client", r"SmartPDM Client[^\n]*\n([0-9][^\n]+|N/A)"),
        ("DMS 61850 Service", r"Qualitrol DMS 61850 Service\s*\n([0-9][^\n]+|N/A)"),
        ("DMS Condition Monitoring SQL", r"Qualitrol DMS Condition Monitoring System SQL\s*\nServer Service CBM\s*\n([0-9][^\n]+|N/A)"),
        ("DMS PDM Protocol", r"Qualitrol DMS PDM Protocol Service\s*\n([0-9][^\n]+|N/A)"),
        ("Report Generation Service", r"Qualitrol DMS Report Generation Service\s*\n([0-9][^\n]+|N/A)"),
        ("Windows", r"Windows Version Number[^\n]*\n([0-9A-Z][^\n]+)"),
        ("Graphics Driver", r"Graphics Driver[^\n]*\n([0-9][^\n]+)"),
        ("SQL Server", r"SQL Server Version Number\s*\n([^\n]+)"),
        ("SQL Server Management Studio", r"SQL Server Management Studio Version\s*\n([0-9][^\n]+)"),
        ("UPS Driver", r"UPS Driver\s*\n([0-9][^\n]+|N/A)"),
    ]
    rows = []
    for item, pattern in software_patterns:
        value = _first_match_any(text, [pattern])
        if value:
            rows.append(SystemBuildItem(item=item, detail=_clean_cell(value)))
    return rows


def _extract_addressing_rows(text: str) -> list[AddressingRow]:
    rows: list[AddressingRow] = []
    seen: set[str] = set()
    pattern = re.compile(r"(?:(PDM/GDM RDC|GDDC\d?|RDC|GDM)\s*\n(?:[^\n]*\n){0,2})?(A86-\d{1,3})\s*\n(192\.168\.\d+\.\d+)", re.IGNORECASE)
    for cabinet, name, address in pattern.findall(text):
        key = f"{cabinet}|{name}|{address}".upper()
        if key in seen:
            continue
        seen.add(key)
        rows.append(AddressingRow(name=name, address=address, cabinet=_clean_cell(cabinet) if cabinet else None))
    return rows


def _first_match_any(text: str, patterns: list[str]) -> str | None:
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1)
    return None


def _clean_cell(value: str | None) -> str | None:
    if not value:
        return None
    return re.sub(r"\s+", " ", value).strip()


def _extract_contents_status(doc: PdfDocument) -> dict[str, str]:
    return {code: item["status"] for code, item in _extract_contents_items(doc).items() if item.get("status")}


def _extract_contents_items(doc: PdfDocument) -> dict[str, dict[str, str]]:
    items: dict[str, dict[str, str]] = {}
    for page in doc.pages:
        if "Contents" not in page.text:
            continue
        lines = clean_lines(page.text)
        current_section: str | None = None
        for index, line in enumerate(lines):
            section_match = re.match(r"Section\s+([A-H])\b", line, re.IGNORECASE)
            if section_match:
                current_section = section_match.group(1).upper()
                continue
            match = re.fullmatch(r"(?:Test|Check)\s+([A-H0-9Il]{1,4})", line, re.IGNORECASE)
            if not match:
                continue
            code = _normalize_test_code(match.group(1), current_section)
            if not code:
                continue
            window: list[str] = []
            for next_line in lines[index + 1 : index + 8]:
                if re.fullmatch(r"(?:Test|Check)\s+[A-H0-9Il]{1,4}", next_line, re.IGNORECASE) or next_line.startswith("Section "):
                    break
                window.append(next_line)
            joined = "\n".join(window)
            status = None
            if re.search(r"\bYes\b", joined, re.IGNORECASE) or "✓" in joined or "" in joined:
                status = "tested"
            elif re.search(r"\bN/A\b", joined):
                status = "n/a"
            name_parts = [item for item in window if not re.fullmatch(r"Yes|No|Tested|N/A", item, re.IGNORECASE)]
            if name_parts:
                items[code] = {"name": name_parts[0].strip(), "status": status or ""}
    return items


def _normalize_test_code(raw_code: str, current_section: str | None = None) -> str | None:
    token = raw_code.upper().replace("I", "1").replace("L", "1")
    if re.fullmatch(r"[A-H]\d+", token):
        return token
    if current_section and re.fullmatch(r"\d+", token):
        return f"{current_section}{token[-1]}"
    return None


def _normalize_ocr_codes(text: str) -> str:
    def replace(match: re.Match[str]) -> str:
        kind = match.group(1)
        code = _normalize_test_code(match.group(2))
        return f"{kind} {code}" if code else match.group(0)

    return re.sub(r"\b(Test|Check)\s+([A-H0-9Il]{1,4})\b", replace, text, flags=re.IGNORECASE)


def _extract_final_checks(doc: PdfDocument) -> list[FinalCheck]:
    checks: list[FinalCheck] = []
    for page in doc.pages:
        normalized = _normalize_ocr_codes(page.text)
        if re.search(r"Check\s+[GH]1:\s*UPS Battery Charge Status", normalized, re.IGNORECASE):
            ups_result = first_match(page.text, r"1\. UPS charged to > 95% capacity\s*\n([^\n]+)")
            checks.append(
                FinalCheck(
                    name="UPS Battery Charge Status",
                    result=ups_result or _extract_operation_result(page.text, r"UPS charged to [^\n]+"),
                    note=first_match(page.text, r"Remarks:\s*\n([^\n]+(?:\n[^\n]+)?)"),
                    page=page.number,
                )
            )
        if re.search(r"Check\s+[GH]2:\s*PCU Watchdog Status", normalized, re.IGNORECASE):
            checks.append(FinalCheck(name="PCU Watchdog Status", result=_extract_operation_result(page.text, r"Watchdog[^\n]+") or "Enabled", page=page.number))
        if re.search(r"Check\s+[GH]3:\s*Substation PC Configuration Status", normalized, re.IGNORECASE):
            checks.append(
                FinalCheck(
                    name="Substation PC Configuration Status",
                    note=first_match(page.text, r"Remarks:\s*([^\n]+)"),
                    page=page.number,
                )
            )
    return checks


def _extract_operation_result(text: str, operation_pattern: str) -> str | None:
    lines = clean_lines(text)
    pattern = re.compile(operation_pattern, re.IGNORECASE)
    for index, line in enumerate(lines):
        if pattern.search(line):
            for next_line in lines[index + 1 : index + 5]:
                if re.fullmatch(r"Pass|Fail|Yes|No|N/A", next_line, re.IGNORECASE):
                    return next_line.title()
    match = re.search(r"Pass/fail\s*\n(?:Remarks:\s*)?(Pass|Fail)", text, re.IGNORECASE)
    return match.group(1).title() if match else None


def _extract_after_fat_evidence(doc: PdfDocument) -> list[EvidenceNote]:
    notes: list[EvidenceNote] = []
    for page in doc.pages:
        if "Screenshot will be provided" in page.text:
            notes.append(EvidenceNote(text="Screenshot will be provided once the UPS charges above 95%.", source_page=page.number))
        if "removed before shutdown/Shipping" in page.text:
            notes.append(EvidenceNote(text="Unnecessary software will be removed before shutdown/shipping.", source_page=page.number))
    return notes


def _merge_post_fat(summary: FatSummary, doc: PdfDocument) -> None:
    text = doc.text
    if not summary.project.project_name:
        summary.project.project_name = _extract_meeting_project_name(text)
    summary.fat_context.venue = value_after_label(text, "Venue") or summary.fat_context.venue
    summary.fat_context.fat_date = value_after_label(text, "Date") or summary.fat_context.fat_date
    summary.fat_context.inspection_type = value_after_label(text, "Inspection Type") or summary.fat_context.inspection_type
    summary.fat_context.date_range = _extract_date_range(text) or summary.fat_context.date_range
    summary.equipment.equipment = value_after_label(text, "Equipment") or summary.equipment.equipment
    summary.equipment.equipment_tag = value_after_label(text, "Equipment Tag") or summary.equipment.equipment_tag
    summary.document_review = _extract_document_review(doc)
    summary.observations.extend(_extract_customer_observations(doc))
    summary.next_actions.extend(_extract_next_actions(doc))


def _extract_date_range(text: str) -> str | None:
    start = value_after_label(text, "Start Date")
    end = value_after_label(text, "End Date")
    if start and end:
        return f"{start} to {end}"
    return None


def _extract_meeting_project_name(text: str) -> str | None:
    lines = clean_lines(text)
    for index, line in enumerate(lines):
        if line == "MINUTES OF MEETING" and index + 1 < len(lines):
            return lines[index + 1]
    return None


def _extract_document_review(doc: PdfDocument) -> DocumentReview:
    rows = 0
    no_changes = 0
    for page in doc.pages:
        rows += len(re.findall(r"\b[A-Z]{1,3}\d{5}\s+Rev\s+[A-Z]\b", page.text))
        no_changes += len(re.findall(r"\bNo changes\b", page.text, re.IGNORECASE))
    summary = None
    if rows:
        summary = f"{rows} referenced drawing/document rows detected; {no_changes} rows state No changes."
    return DocumentReview(summary=summary, referenced_document_count=rows or None, rows_with_no_changes=no_changes or None)


def _extract_customer_observations(doc: PdfDocument) -> list[Observation]:
    observations: list[Observation] = []
    for page in doc.pages:
        if "Customer Comments and Observations" not in page.text:
            continue
        lines = clean_lines(page.text)
        joined = " ".join(lines)
        if "Earth Wiring" in joined:
            observations.append(
                Observation(
                    text="Earth wiring colour should follow US standards; SE to check end-user acceptability.",
                    owner="SE",
                    status="Pending",
                    source_page=page.number,
                )
            )
        if "nominal values" in joined:
            observations.append(
                Observation(
                    text="Nominal values lock after FAT/SAT requested; Viewer Group created without alarm/configuration access.",
                    owner="Qualitrol",
                    status="Completed / controlled access",
                    source_page=page.number,
                )
            )
    return observations


def _extract_next_actions(doc: PdfDocument) -> list[ActionItem]:
    actions: list[ActionItem] = []
    for page in doc.pages:
        text = page.text
        if "photographic evidence" in text:
            actions.append(ActionItem(action="Provide photographic evidence prior to shipping where noted.", owner="Qualitrol", state="Before shipping", source_page=page.number))
        if "SE to check with end user" in text:
            actions.append(ActionItem(action="Confirm earth wiring colour acceptability with end user.", owner="SE", state="Pending", source_page=page.number))
        if "Viewer Group" in text:
            actions.append(ActionItem(action="Use restricted Viewer Group for nominal values access control.", owner="Qualitrol", state="Completed", source_page=page.number))
    return actions


def _infer_readiness(summary: FatSummary) -> ReadinessPosture:
    if any(item.state and "Pending" in item.state for item in summary.next_actions):
        return ReadinessPosture.CONTROLLED_FOLLOW_UP
    if summary.final_checks or summary.test_coverage.detected_test_count:
        return ReadinessPosture.READY_WITH_NOTES
    return ReadinessPosture.UNKNOWN
