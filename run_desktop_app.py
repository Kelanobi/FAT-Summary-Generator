import sys

from fat_summary_app.extract import extract_fat_summary
from fat_summary_app.models import FatSummary
from fat_summary_app.render import render_visual_summary_html
from fat_summary_app.web_app import main


if __name__ == "__main__":
    if "--smoke-test" in sys.argv:
        html = render_visual_summary_html(FatSummary())
        if "Factory Acceptance Test Summary Dashboard" not in html:
            raise SystemExit("Smoke test failed")
        print("Smoke test passed")
        raise SystemExit(0)
    if "--extract-json" in sys.argv:
        index = sys.argv.index("--extract-json")
        try:
            output = sys.argv[index + 1]
            pdfs = sys.argv[index + 2 :]
        except IndexError as exc:
            raise SystemExit("Usage: --extract-json OUTPUT_PATH PDF_PATH [PDF_PATH ...]") from exc
        if not pdfs:
            raise SystemExit("Usage: --extract-json OUTPUT_PATH PDF_PATH [PDF_PATH ...]")
        extract_fat_summary(pdfs).write_json(output)
        raise SystemExit(0)
    main()
