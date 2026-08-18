from __future__ import annotations

import argparse
import json
from pathlib import Path

from fat_summary_app.extract import extract_fat_summary
from fat_summary_app.render import build_template_context, render_visual_summary_html, write_visual_summary_pdf


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Extract structured FAT summary data from PDF reports.")
    parser.add_argument("sources", nargs="+", help="PDF source files to extract.")
    parser.add_argument("-o", "--output", required=True, help="JSON output path.")
    parser.add_argument("--template-context", help="Optional four-page template context JSON output path.")
    parser.add_argument("--html", help="Optional rendered visual summary HTML output path.")
    parser.add_argument("--pdf", help="Optional rendered visual summary PDF output path.")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    summary = extract_fat_summary([Path(source) for source in args.sources])
    summary.write_json(args.output)
    print(f"Wrote {args.output}")
    if args.template_context:
        Path(args.template_context).write_text(
            json.dumps(build_template_context(summary), indent=2),
            encoding="utf-8",
        )
        print(f"Wrote {args.template_context}")
    if args.html:
        Path(args.html).write_text(render_visual_summary_html(summary), encoding="utf-8")
        print(f"Wrote {args.html}")
    if args.pdf:
        write_visual_summary_pdf(summary, args.pdf)
        print(f"Wrote {args.pdf}")


if __name__ == "__main__":
    main()
