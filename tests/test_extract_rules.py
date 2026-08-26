from __future__ import annotations

from fat_summary_app.extract import extract_fat_summary
from fat_summary_app.extract.rules import _extract_voltage
from fat_summary_app.models import Equipment, FatSummary, Project
from fat_summary_app.models.report import AddressingRow
from fat_summary_app.models.report import ReadinessPosture, SystemVariant
from fat_summary_app.render import build_template_context, build_visual_template_context, render_visual_summary_html, write_visual_summary_pdf
from fat_summary_app.render.reportlab_pdf import _dashboard_check_counts, _scope_tiles
from fat_summary_app.review import apply_review_edits, get_editable_values
from fat_summary_app.models.report import TestCoverage as CoverageModel
from fat_summary_app.models.report import TestItem as CoverageItem
from fat_summary_app.models.report import PictureEvidence, SourceDocument
from fat_summary_app.render.reportlab_pdf import _extract_trailing_pictures, _manual_pictures


AFIF = r"C:\Users\kelvin.obi\Desktop\50577444 - AFIF1 PSS1 - PDM GDM - After FAT Procedure.pdf"
GOODINGS = r"S:\Manufacturing\Public\2 Jobfiles Released\50538114\FAT\50538114 - Goodings Grove 345kV SS - GDM - FAT - Snag Clearance.pdf"
GOODINGS_FULL_GDM = r"S:\Manufacturing\Public\2 Jobfiles Released\50538114\FAT\50538114 - Goodings Grove 345kV SS - GDM - FAT Procedure Customer Witness Signed.pdf"


def test_extracts_core_after_fat_metadata() -> None:
    summary = extract_fat_summary([AFIF])

    assert summary.project.manufacturing_number == "50577444"
    assert summary.project.substation == "AFIF 1 SS1"
    assert summary.project.customer == "Siemens High Voltage China"
    assert summary.equipment.system_type == "PDMG-RH & GDM"
    assert summary.system_variant == SystemVariant.PDM_GDM
    assert summary.test_coverage.detected_test_count >= 30
    assert any(check.name == "UPS Battery Charge Status" for check in summary.final_checks)


def test_extracts_post_fat_observations_and_actions() -> None:
    summary = extract_fat_summary([GOODINGS])

    assert summary.equipment.equipment_tag == "50538114"
    assert summary.system_variant == SystemVariant.GDM
    assert summary.document_review.referenced_document_count is not None
    assert summary.document_review.referenced_document_count >= 20
    assert any("Earth wiring" in observation.text for observation in summary.observations)
    assert any(action.owner == "SE" for action in summary.next_actions)


def test_extracts_full_gdm_fat_report_details() -> None:
    summary = extract_fat_summary([GOODINGS_FULL_GDM], system_variant="gdm")

    assert summary.system_variant == SystemVariant.GDM
    assert summary.project.project_name == "Goodings Grove 345kV - Moisture Monitoring"
    assert summary.project.substation == "Gooding Grove GIS Substation"
    assert summary.project.customer == "Siemens Energy"
    assert summary.project.voltage == "345kV"
    assert summary.project.manufacturing_number == "50538114"
    assert summary.fat_context.document_no == "DMT00196"
    assert summary.equipment.sensor_count == 564
    assert summary.equipment.gdm_module_count == 43
    assert summary.test_coverage.detected_test_count >= 21
    assert all(item.status == "tested" for item in summary.test_coverage.tests)
    assert any(check.name == "UPS Battery Charge Status" and check.result == "Pass" for check in summary.final_checks)


def test_blank_voltage_does_not_capture_next_label() -> None:
    text = "Project\nAFIF\nVoltage\nCustomer\nSiemens Energy\n"

    assert _extract_voltage(text) is None


def test_combined_summary_sets_controlled_follow_up() -> None:
    summary = extract_fat_summary([AFIF, GOODINGS])

    assert summary.readiness_posture == ReadinessPosture.CONTROLLED_FOLLOW_UP
    assert len(summary.source_documents) == 2


def test_builds_four_page_template_context() -> None:
    summary = extract_fat_summary([AFIF, GOODINGS])
    context = build_template_context(summary)

    assert set(context) == {"page_1", "page_2", "page_3", "page_4"}
    assert context["page_1"]["manufacturing_number"] == "50577444"
    assert context["page_2"]["test_count"] >= 30
    assert context["page_4"]["next_actions"]


def test_builds_canva_derived_visual_context() -> None:
    summary = extract_fat_summary([AFIF, GOODINGS])
    context = build_visual_template_context(summary)

    assert context["variant"] == "pdmg"
    assert context["variant_title"] == "PDM & GDM"
    assert context["dashboard_title"] == "Factory Acceptance Test Summary Dashboard"
    assert context["section_range"] == "Sections A to H"
    assert len(context["section_rows"]) == 8
    top = {item["label"]: item["value"] for item in context["top_metrics"]}
    assert top["Sensors"] == "52"
    assert top["PDM OCUs"] == "11"
    assert top["GDM DAUs"] == "5"


def test_renders_visual_summary_without_signoff_block() -> None:
    summary = extract_fat_summary([AFIF, GOODINGS])
    html = render_visual_summary_html(summary)

    assert "Factory Acceptance Test Summary Dashboard" in html
    assert "System Build & Configuration Dashboard" in html
    assert "FAT Test Performance Dashboard" in html
    assert "Signature" not in html
    assert "Approval" not in html
    assert "Review note" not in html
    assert "Source pages" not in html
    assert "Source hash" not in html
    assert "Release confidence" not in html


def test_visual_summary_uses_fat_result_language() -> None:
    summary = extract_fat_summary([AFIF])
    context = build_visual_template_context(summary)
    html = render_visual_summary_html(summary)

    assert context["final_status_line"] == "COMPLETED / PASSED"
    assert context["final_status_note"] == "The FAT has been completed and passed."
    assert "UPS Battery Charge Status: 90% After FAT, PASS" in context["timeline_note"]
    assert "Physical Inspection" in html
    assert "Software Baseline" in html
    assert "UPS Charge Evidence" in html
    assert "Ready for review" not in html
    assert "extracted from" not in html


def test_visual_context_supports_gdm_only_language() -> None:
    summary = extract_fat_summary([GOODINGS])
    context = build_visual_template_context(summary)
    html = render_visual_summary_html(summary)

    assert summary.system_variant == SystemVariant.GDM
    assert context["variant"] == "gdm"
    assert context["variant_title"] == "GDM"
    assert context["dashboard_title"] == "GDM Factory Acceptance Test Summary Dashboard"
    assert context["section_range"] == "GDM-focused FAT / post-FAT sections"
    assert "GDM Factory Acceptance Test Summary Dashboard" in html
    assert "Gas Density Monitoring" in html
    assert "OCU and PD event profile" not in html


def test_visual_context_supports_pdm_only_language() -> None:
    summary = FatSummary(
        project=Project(project_name="PDM Sample Project", manufacturing_number="50564066", voltage="500kV"),
        equipment=Equipment(system_type="PDMG-RH", ocu_model="15 x 6CH, 4 x 3CH", operating_frequency="60Hz", number_of_ocus="19 OCU"),
        system_variant=SystemVariant.PDM,
    )
    context = build_visual_template_context(summary)

    assert context["variant"] == "pdm"
    assert context["variant_title"] == "PDM"
    assert context["dashboard_title"] == "PDM Factory Acceptance Test Summary Dashboard"
    assert context["section_range"] == "Sections A to F"
    assert context["profile_title"] == "OCU and PD event profile"
    top = {item["label"]: item["value"] for item in context["top_metrics"]}
    assert top["PDM OCUs"] == "19"
    assert "GDM/final" not in {row["label"] for row in context["profile_rows"]}


def test_dashboard_supports_large_pdm_and_gdm_counts() -> None:
    pdm = FatSummary(
        project=Project(project_name="Large PDM", manufacturing_number="50564066", voltage="500kV"),
        equipment=Equipment(system_type="PDMG-RH", number_of_ocus="20 OCU", sensor_count=120, operating_frequency="60Hz"),
        system_variant=SystemVariant.PDM,
    )
    gdm = FatSummary(
        project=Project(project_name="Large GDM", manufacturing_number="50564067", voltage="345kV"),
        equipment=Equipment(equipment="Gas Density Monitoring System", sensor_count=30, gdm_module_count=30, operating_frequency="60Hz"),
        system_variant=SystemVariant.GDM,
    )
    gdm.system_build.addressing = [AddressingRow(name=f"A86-{idx:02d}", address=f"192.168.6.{idx}") for idx in range(1, 31)]

    pdm_top = {item["label"]: item["value"] for item in build_visual_template_context(pdm)["top_metrics"]}
    gdm_context = build_visual_template_context(gdm)
    gdm_top = {item["label"]: item["value"] for item in gdm_context["top_metrics"]}

    assert pdm_top["PDM OCUs"] == "20"
    assert gdm_top["GDM Sensors"] == "30"
    assert gdm_top["A86 Modules"] == "30"
    assert len(gdm_context["addressing_rows"]) == 8
    assert "showing first 8" in gdm_context["addressing_summary"]


def test_visual_context_does_not_invent_missing_values() -> None:
    summary = FatSummary(
        project=Project(project_name="PDM Sample Project", manufacturing_number="50564066"),
        equipment=Equipment(system_type="PDMG-RH"),
        system_variant=SystemVariant.PDM,
    )
    context = build_visual_template_context(summary)
    metrics = {item["label"]: item["value"] for item in context["cover_metrics"]}

    assert context["variant"] == "pdm"
    assert metrics["OCUs"] == "-"
    assert metrics["Voltage"] == "-"
    assert metrics["Frequency"] == "-"
    assert metrics["Sensor / channel positions"] == "-"
    assert metrics["Listed FAT items"] == "-"


def test_writes_visual_summary_pdf(tmp_path) -> None:
    summary = extract_fat_summary([GOODINGS])
    output = tmp_path / "summary.pdf"

    write_visual_summary_pdf(summary, output)

    assert output.exists()
    assert output.stat().st_size > 1000


def test_trailing_picture_extraction_keeps_all_pictures_from_last_six_pages(tmp_path) -> None:
    import io

    import fitz
    from PIL import Image

    image_file = io.BytesIO()
    Image.new("RGB", (80, 80), color=(210, 30, 30)).save(image_file, format="PNG")
    image_bytes = image_file.getvalue()

    doc = fitz.open()
    for page_index in range(8):
        page = doc.new_page(width=595, height=842)
        page.insert_text((40, 40), "PICTURES" if page_index == 6 else f"Page {page_index + 1}")
        if page_index == 6:
            for idx in range(7):
                x = 40 + (idx % 3) * 170
                y = 90 + (idx // 3) * 210
                page.insert_text((x, y - 12), f"Image {idx + 1}: FAT evidence {idx + 1}")
                page.insert_image(fitz.Rect(x, y, x + 120, y + 120), stream=image_bytes)
    source_pdf = tmp_path / "pictures.pdf"
    doc.save(source_pdf)
    doc.close()

    summary = FatSummary(source_documents=[SourceDocument(label="pictures", path=str(source_pdf), pages=8, sha256="test")])

    pictures = _extract_trailing_pictures(summary)

    assert len(pictures) == 7
    assert pictures[0].caption == "Image 1: FAT evidence 1"


def test_uploaded_picture_evidence_is_the_report_picture_source(tmp_path) -> None:
    import io

    from PIL import Image

    image_path = tmp_path / "uploaded.png"
    image_file = io.BytesIO()
    Image.new("RGB", (100, 80), color=(20, 120, 180)).save(image_file, format="PNG")
    image_path.write_bytes(image_file.getvalue())
    summary = FatSummary(picture_evidence=[PictureEvidence(path=str(image_path), caption="Uploaded OCU evidence")])

    pictures = _manual_pictures(summary)

    assert len(pictures) == 1
    assert pictures[0].caption == "Uploaded OCU evidence"


def test_completed_fat_na_items_are_excluded_from_completion() -> None:
    summary = FatSummary(
        test_coverage=CoverageModel(
            detected_test_count=25,
            tests=[
                *[CoverageItem(code=f"A{idx}", name=f"Check {idx}", status="tested") for idx in range(1, 24)],
                CoverageItem(code="A24", name="Check 24", status=None),
                CoverageItem(code="A25", name="Check 25", status="n/a"),
            ],
        )
    )

    counts = _dashboard_check_counts(summary)

    assert counts["total"] == 25
    assert counts["passed"] == 24
    assert counts["na"] == 1
    assert counts["failed"] == 0
    assert counts["completion"] == 100


def test_scope_tiles_calculate_ocu_channels_and_gdm_sensors() -> None:
    summary = FatSummary(
        equipment=Equipment(
            system_type="PDM 5x5CH, 2x4CH, 2x3Ch, 1x2Ch, 1x1Ch & GDM System for 52 Sensors",
            gdm_module_count=5,
            sensor_count=52,
            operating_frequency="50Hz",
        ),
        system_variant=SystemVariant.PDM_GDM,
    )

    tiles = {label: (value, note) for label, value, note in _scope_tiles(summary, summary.system_variant)}

    assert tiles["OCU"] == ("11", "Grouped OCU total")
    assert tiles["OCU channel"] == ("42", "")
    assert tiles["GDM Module"] == ("5", "")
    assert tiles["GDM sensors"] == ("52", "")
    assert "GDDC cabinets" not in tiles


def test_reviewed_total_ocu_overrides_formula_count() -> None:
    summary = FatSummary(
        equipment=Equipment(ocu_model="12X6Ch, 6X3Ch"),
        system_variant=SystemVariant.PDM,
    )

    tiles = {label: value for label, value, _note in _scope_tiles(summary, summary.system_variant)}
    assert tiles["OCU"] == "18"

    values = get_editable_values(summary)
    values["equipment.ocu_model"] = "20"
    updated = apply_review_edits(summary, values)
    tiles = {label: value for label, value, _note in _scope_tiles(updated, updated.system_variant)}

    assert tiles["OCU"] == "20"


def test_applies_review_edits() -> None:
    summary = extract_fat_summary([GOODINGS])
    values = get_editable_values(summary)
    values["project.customer"] = "Reviewed Customer"
    values["equipment.sensor_count"] = "42"
    values["equipment.gdm_module_count"] = "7"
    values["system_variant"] = "gdm"
    values["readiness_posture"] = "ready_with_notes"

    updated = apply_review_edits(summary, values)

    assert updated.project.customer == "Reviewed Customer"
    assert updated.equipment.sensor_count == 42
    assert updated.equipment.gdm_module_count == 7
    assert updated.system_variant == SystemVariant.GDM
    assert updated.readiness_posture == ReadinessPosture.READY_WITH_NOTES
    assert updated.export_manifest.user_edits_made is True


def test_desktop_app_module_imports() -> None:
    import fat_summary_app.desktop_app as desktop_app

    assert desktop_app.FatSummaryDesktopApp is not None
