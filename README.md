# FAT Summary App Prototype

Offline-first prototype for extracting structured data from FAT reports and preparing it for a four-page executive engineering summary.

Current scope:

- Parse text-based PDF reports with PyMuPDF.
- Extract project metadata, equipment scope, test coverage, final checks, drawing review, observations, and next-action signals.
- Normalize results into Pydantic models.
- Export JSON snapshots that can feed the future review UI and report template.
- Render a Canva-derived four-page Qualitrol visual summary HTML template.

This prototype intentionally does not make snags the main focus and does not include approval or sign-off blocks.

## Render Outputs

The current visual template is based on the user's new Canva/PDF design direction:

1. Executive FAT Summary
2. Operational Test Coverage
3. Engineering Findings & Evidence
4. FAT Closeout Summary

The app renderer keeps the look and information architecture, but replaces the Canva signature/approval area with traceability and review-note panels.

## System Variants

The extraction model now records a `system_variant` enum:

- `pdm`
- `gdm`
- `pdmg`
- `unknown`

The renderer uses this value to adapt titles, metrics, section coverage, evidence labels, and closeout language. PDM reports focus on OCU/UHF/PD event evidence. GDM reports focus on gas density equipment, drawing review, observations, and delivery/evidence actions. Combined PDM/GDM reports use the broader A-H coverage layout.

Example CLI:

```powershell
python -m fat_summary_app.cli "source-a.pdf" "source-b.pdf" `
  -o extracted.json `
  --template-context template-context.json `
  --html visual-summary.html `
  --pdf visual-summary.pdf
```

## Desktop App Flow

Run the local desktop prototype:

```powershell
python -m fat_summary_app.desktop_app
```

Workflow:

1. Click **Add FAT PDF(s)**.
2. Select the full FAT report PDF, and optionally a related post-FAT discussion/clearance PDF.
3. Click **Extract Report Data**.
4. Review and edit extracted project, equipment, FAT context, system variant, and readiness fields.
5. Open the browser preview.
6. Choose where to save the generated summary PDF.
7. Click **Generate PDF**.

The app extracts locally, detects the system variant, renders the Canva-derived four-page visual summary, and saves the final PDF.

Current desktop tabs:

- **Import**: add or remove source PDFs.
- **Review**: inspect and correct extracted fields before export.
- **Preview**: generate and open a local HTML preview.
- **Export**: render the final PDF.

The PDF renderer uses installed Chrome or Edge through Playwright when available. If a browser renderer is unavailable, the app falls back to a simpler native PDF renderer.
