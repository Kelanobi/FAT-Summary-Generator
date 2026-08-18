from __future__ import annotations

import os
import tempfile
import threading
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
import tkinter as tk

from fat_summary_app.extract import extract_fat_summary
from fat_summary_app.models import FatSummary
from fat_summary_app.models.report import ReadinessPosture, SystemVariant
from fat_summary_app.render import write_visual_summary_pdf
from fat_summary_app.review import EDITABLE_FIELDS, apply_review_edits, get_editable_values


class FatSummaryDesktopApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Qualitrol FAT Summary Generator")
        self.geometry("1040x720")
        self.minsize(920, 620)

        self.source_paths: list[Path] = []
        self.extracted_summary: FatSummary | None = None
        self.summary: FatSummary | None = None
        self.field_vars: dict[str, tk.StringVar] = {}
        self.status_var = tk.StringVar(value="Ready")
        self.output_var = tk.StringVar()
        self.variant_var = tk.StringVar(value="auto")
        self.preview_path: Path | None = None
        self.review_dirty = False

        self._build_ui()

    def _build_ui(self) -> None:
        root = ttk.Frame(self, padding=16)
        root.pack(fill=tk.BOTH, expand=True)

        header = ttk.Frame(root)
        header.pack(fill=tk.X)
        ttk.Label(header, text="Qualitrol FAT Summary Generator", font=("Arial", 18, "bold")).pack(side=tk.LEFT)
        ttk.Label(header, textvariable=self.status_var, foreground="#5f6970").pack(side=tk.RIGHT)

        self.tabs = ttk.Notebook(root)
        self.tabs.pack(fill=tk.BOTH, expand=True, pady=(14, 0))

        self.import_tab = ttk.Frame(self.tabs, padding=14)
        self.review_tab = ttk.Frame(self.tabs, padding=14)
        self.preview_tab = ttk.Frame(self.tabs, padding=14)
        self.export_tab = ttk.Frame(self.tabs, padding=14)
        self.tabs.add(self.import_tab, text="1. Import")
        self.tabs.add(self.review_tab, text="2. Review")
        self.tabs.add(self.preview_tab, text="3. Preview")
        self.tabs.add(self.export_tab, text="4. Export")

        self._build_import_tab()
        self._build_review_tab()
        self._build_preview_tab()
        self._build_export_tab()

    def _build_import_tab(self) -> None:
        ttk.Label(self.import_tab, text="Select full FAT report PDF files", font=("Arial", 13, "bold")).pack(anchor=tk.W)
        ttk.Label(
            self.import_tab,
            text="Add the main FAT report. You can also add related post-FAT discussion or clearance PDFs.",
            foreground="#5f6970",
        ).pack(anchor=tk.W, pady=(3, 12))

        row = ttk.Frame(self.import_tab)
        row.pack(fill=tk.X)
        ttk.Button(row, text="Add PDF(s)", command=self._select_sources).pack(side=tk.LEFT)
        ttk.Button(row, text="Remove Selected", command=self._remove_selected_source).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(row, text="Clear", command=self._clear_sources).pack(side=tk.LEFT, padx=(8, 0))

        mode_row = ttk.Frame(self.import_tab)
        mode_row.pack(fill=tk.X, pady=(12, 0))
        ttk.Label(mode_row, text="System Type").pack(side=tk.LEFT)
        ttk.Combobox(
            mode_row,
            textvariable=self.variant_var,
            values=["auto", SystemVariant.PDM.value, SystemVariant.GDM.value, SystemVariant.PDM_GDM.value],
            state="readonly",
            width=18,
        ).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Label(
            mode_row,
            text="Choose PDM, GDM or PDM/GDM when known; Auto uses document detection.",
            foreground="#5f6970",
        ).pack(side=tk.LEFT, padx=12)

        self.source_listbox = tk.Listbox(self.import_tab, height=14)
        self.source_listbox.pack(fill=tk.BOTH, expand=True, pady=12)

        bottom = ttk.Frame(self.import_tab)
        bottom.pack(fill=tk.X)
        self.extract_button = ttk.Button(bottom, text="Extract Report Data", command=self._extract)
        self.extract_button.pack(side=tk.LEFT)
        ttk.Label(bottom, text="Extraction is local. Nothing is uploaded.", foreground="#5f6970").pack(side=tk.LEFT, padx=12)

    def _build_review_tab(self) -> None:
        self.review_canvas = tk.Canvas(self.review_tab, highlightthickness=0)
        scrollbar = ttk.Scrollbar(self.review_tab, orient=tk.VERTICAL, command=self.review_canvas.yview)
        self.review_frame = ttk.Frame(self.review_canvas)
        self.review_frame.bind("<Configure>", lambda _event: self.review_canvas.configure(scrollregion=self.review_canvas.bbox("all")))
        self.review_canvas.create_window((0, 0), window=self.review_frame, anchor="nw")
        self.review_canvas.configure(yscrollcommand=scrollbar.set)
        self.review_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        ttk.Label(self.review_frame, text="Review extracted fields", font=("Arial", 13, "bold")).grid(row=0, column=0, columnspan=2, sticky=tk.W, pady=(0, 10))
        ttk.Label(self.review_frame, text="System Variant").grid(row=1, column=0, sticky=tk.W, pady=4)
        self.field_vars["system_variant"] = tk.StringVar(value=SystemVariant.UNKNOWN.value)
        self.field_vars["system_variant"].trace_add("write", self._mark_review_dirty)
        ttk.Combobox(
            self.review_frame,
            textvariable=self.field_vars["system_variant"],
            values=[item.value for item in SystemVariant],
            state="readonly",
            width=42,
        ).grid(row=1, column=1, sticky=tk.W, pady=4)

        ttk.Label(self.review_frame, text="Readiness").grid(row=2, column=0, sticky=tk.W, pady=4)
        self.field_vars["readiness_posture"] = tk.StringVar(value=ReadinessPosture.UNKNOWN.value)
        self.field_vars["readiness_posture"].trace_add("write", self._mark_review_dirty)
        ttk.Combobox(
            self.review_frame,
            textvariable=self.field_vars["readiness_posture"],
            values=[item.value for item in ReadinessPosture],
            state="readonly",
            width=42,
        ).grid(row=2, column=1, sticky=tk.W, pady=4)

        row_index = 3
        for path, label in EDITABLE_FIELDS.items():
            ttk.Label(self.review_frame, text=label).grid(row=row_index, column=0, sticky=tk.W, pady=4, padx=(0, 14))
            var = tk.StringVar()
            var.trace_add("write", self._mark_review_dirty)
            self.field_vars[path] = var
            ttk.Entry(self.review_frame, textvariable=var, width=72).grid(row=row_index, column=1, sticky=tk.EW, pady=4)
            row_index += 1

        actions = ttk.Frame(self.review_frame)
        actions.grid(row=row_index, column=0, columnspan=2, sticky=tk.W, pady=(14, 0))
        ttk.Button(actions, text="Apply Review Edits", command=self._apply_edits).pack(side=tk.LEFT)
        ttk.Button(actions, text="Preview Summary", command=self._preview).pack(side=tk.LEFT, padx=(8, 0))
        self.review_frame.columnconfigure(1, weight=1)

    def _build_preview_tab(self) -> None:
        ttk.Label(self.preview_tab, text="Preview", font=("Arial", 13, "bold")).pack(anchor=tk.W)
        ttk.Label(
            self.preview_tab,
            text="Open the PDF preview to inspect the same layout used by export.",
            foreground="#5f6970",
        ).pack(anchor=tk.W, pady=(3, 12))
        row = ttk.Frame(self.preview_tab)
        row.pack(fill=tk.X)
        ttk.Button(row, text="Refresh Preview", command=self._preview).pack(side=tk.LEFT)
        ttk.Button(row, text="Open PDF Preview", command=self._open_preview).pack(side=tk.LEFT, padx=(8, 0))
        self.preview_text = tk.Text(self.preview_tab, height=22, wrap=tk.WORD)
        self.preview_text.pack(fill=tk.BOTH, expand=True, pady=12)
        self.preview_text.insert(tk.END, "Preview details will appear here after extraction.")
        self.preview_text.configure(state=tk.DISABLED)

    def _build_export_tab(self) -> None:
        ttk.Label(self.export_tab, text="Export visual summary PDF", font=("Arial", 13, "bold")).pack(anchor=tk.W)
        ttk.Label(
            self.export_tab,
            text="The PDF uses the browser-grade renderer when Chrome or Edge is available.",
            foreground="#5f6970",
        ).pack(anchor=tk.W, pady=(3, 12))
        output_row = ttk.Frame(self.export_tab)
        output_row.pack(fill=tk.X, pady=(0, 12))
        ttk.Label(output_row, text="Output PDF").pack(side=tk.LEFT)
        ttk.Entry(output_row, textvariable=self.output_var).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=8)
        ttk.Button(output_row, text="Save As...", command=self._select_output).pack(side=tk.LEFT)

        row = ttk.Frame(self.export_tab)
        row.pack(fill=tk.X)
        self.export_button = ttk.Button(row, text="Generate PDF", command=self._export_pdf)
        self.export_button.pack(side=tk.LEFT)
        ttk.Button(row, text="Open Output Folder", command=self._open_output_folder).pack(side=tk.LEFT, padx=(8, 0))

    def _select_sources(self) -> None:
        paths = filedialog.askopenfilenames(
            title="Select FAT report PDF files",
            filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")],
        )
        for raw_path in paths:
            path = Path(raw_path)
            if path not in self.source_paths:
                self.source_paths.append(path)
                self.source_listbox.insert(tk.END, str(path))
        if self.source_paths and not self.output_var.get():
            default = self.source_paths[0].with_name(f"{self.source_paths[0].stem}_visual_summary.pdf")
            self.output_var.set(str(default))

    def _remove_selected_source(self) -> None:
        selected = list(self.source_listbox.curselection())
        for index in reversed(selected):
            self.source_listbox.delete(index)
            del self.source_paths[index]

    def _clear_sources(self) -> None:
        self.source_paths.clear()
        self.source_listbox.delete(0, tk.END)
        self.extracted_summary = None
        self.summary = None
        self.status_var.set("Ready")

    def _extract(self) -> None:
        if not self.source_paths:
            messagebox.showwarning("No source PDFs", "Add at least one FAT report PDF first.")
            return
        self.extract_button.config(state=tk.DISABLED)
        self.status_var.set("Extracting...")
        threading.Thread(target=self._extract_worker, daemon=True).start()

    def _extract_worker(self) -> None:
        try:
            summary = extract_fat_summary(self.source_paths, system_variant=self.variant_var.get())
        except Exception as exc:  # pragma: no cover - UI error path
            self.after(0, self._operation_failed, "Extraction failed", exc)
            return
        self.after(0, self._extraction_succeeded, summary)

    def _extraction_succeeded(self, summary: FatSummary) -> None:
        self.extracted_summary = summary
        self.summary = summary
        self.extract_button.config(state=tk.NORMAL)
        self._load_review_fields(summary)
        self.status_var.set(f"Extracted {summary.system_variant.value.upper()} report")
        self.tabs.select(self.review_tab)

    def _load_review_fields(self, summary: FatSummary) -> None:
        for path, value in get_editable_values(summary).items():
            if path in self.field_vars:
                self.field_vars[path].set(value)
        self.review_dirty = False

    def _apply_edits(self) -> None:
        summary = self._current_review_summary(show_errors=True)
        if summary:
            self.summary = summary
            self.review_dirty = False
            self.status_var.set("Review edits applied")

    def _current_review_summary(self, show_errors: bool = False) -> FatSummary | None:
        base_summary = self.extracted_summary or self.summary
        if not base_summary:
            if show_errors:
                messagebox.showwarning("No extraction", "Extract report data before reviewing.")
            return None
        try:
            return apply_review_edits(base_summary, self._review_values())
        except ValueError as exc:
            if show_errors:
                messagebox.showerror("Review edit error", f"Check numeric fields such as sensor count and GDM module count.\n\n{exc}")
            self.status_var.set("Review edit error")
            return None

    def _review_values(self) -> dict[str, str]:
        self.update_idletasks()
        return {path: var.get() for path, var in self.field_vars.items()}

    def _mark_review_dirty(self, *_args: object) -> None:
        if self.summary:
            self.review_dirty = True
            self.status_var.set("Review edits pending")

    def _preview(self) -> None:
        if not self.summary:
            messagebox.showwarning("No extraction", "Extract report data before previewing.")
            return
        summary = self._current_review_summary(show_errors=True)
        if not summary:
            return
        self.summary = summary
        self.review_dirty = False
        preview = Path(tempfile.gettempdir()) / "qualitrol_fat_summary_preview.pdf"
        write_visual_summary_pdf(summary, preview)
        self.preview_path = preview
        self._write_preview_details(summary)
        self.tabs.select(self.preview_tab)
        webbrowser.open(preview.resolve().as_uri())

    def _write_preview_details(self, summary: FatSummary) -> None:
        lines = [
            f"Variant: {summary.system_variant.value}",
            f"Readiness: {summary.readiness_posture.value}",
            f"Project: {summary.project.project_name or '-'}",
            f"Substation: {summary.project.substation or '-'}",
            f"Customer: {summary.project.customer or '-'}",
            f"Manufacturing No.: {summary.project.manufacturing_number or summary.equipment.equipment_tag or '-'}",
            f"System Type: {summary.equipment.system_type or summary.equipment.equipment or '-'}",
            f"Sensor Count: {summary.equipment.sensor_count or '-'}",
            f"GDM Module Count: {summary.equipment.gdm_module_count or '-'}",
            f"Detected tests/checks: {summary.test_coverage.detected_test_count}",
            f"Observations: {len(summary.observations)}",
            f"Next actions: {len(summary.next_actions)}",
            "",
            f"Preview file: {self.preview_path}",
        ]
        self.preview_text.configure(state=tk.NORMAL)
        self.preview_text.delete("1.0", tk.END)
        self.preview_text.insert(tk.END, "\n".join(lines))
        self.preview_text.configure(state=tk.DISABLED)

    def _open_preview(self) -> None:
        if not self.preview_path or not self.preview_path.exists():
            self._preview()
            return
        webbrowser.open(self.preview_path.resolve().as_uri())

    def _select_output(self) -> None:
        initial = self._default_output_path()
        path = filedialog.asksaveasfilename(
            parent=self,
            title="Save visual summary PDF",
            initialdir=str(initial.parent),
            initialfile=initial.name,
            defaultextension=".pdf",
            filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")],
        )
        if path:
            self.output_var.set(path)

    def _default_output_path(self) -> Path:
        current = self.output_var.get().strip()
        if current:
            return Path(current)
        if self.source_paths:
            return self.source_paths[0].with_name(f"{self.source_paths[0].stem}_visual_summary.pdf")
        return Path.home() / "Documents" / "Qualitrol_FAT_visual_summary.pdf"

    def _export_pdf(self) -> None:
        if not self.summary:
            messagebox.showwarning("No extraction", "Extract report data before exporting.")
            return
        output = self.output_var.get().strip()
        if not output:
            self._select_output()
            output = self.output_var.get().strip()
            if not output:
                self.status_var.set("Export cancelled")
                return
        summary = self._current_review_summary(show_errors=True)
        if not summary:
            return
        self.summary = summary
        self.review_dirty = False
        self.export_button.config(state=tk.DISABLED)
        self.status_var.set("Rendering PDF...")
        threading.Thread(target=self._export_worker, args=(summary, Path(output)), daemon=True).start()

    def _export_worker(self, summary: FatSummary, output: Path) -> None:
        try:
            output.parent.mkdir(parents=True, exist_ok=True)
            write_visual_summary_pdf(summary, output)
        except Exception as exc:  # pragma: no cover - UI error path
            self.after(0, self._operation_failed, "Export failed", exc)
            return
        self.after(0, self._export_succeeded, output)

    def _export_succeeded(self, output: Path) -> None:
        self.export_button.config(state=tk.NORMAL)
        self.status_var.set(f"Saved: {output}")
        messagebox.showinfo("Summary generated", f"Saved visual summary PDF:\n{output}")

    def _open_output_folder(self) -> None:
        output = self.output_var.get().strip()
        if output:
            folder = Path(output).parent
            if folder.exists():
                os.startfile(folder)  # type: ignore[attr-defined]

    def _operation_failed(self, title: str, exc: Exception) -> None:
        self.extract_button.config(state=tk.NORMAL)
        self.export_button.config(state=tk.NORMAL)
        self.status_var.set(title)
        messagebox.showerror(title, str(exc))


def main() -> None:
    app = FatSummaryDesktopApp()
    app.mainloop()


if __name__ == "__main__":
    main()
