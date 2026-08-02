from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from paperposter.reading_report import render_reading_report  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Render a paper reading report.")
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument("--no-pdf", action="store_true")
    args = parser.parse_args()
    run_dir = args.run_dir.resolve()
    html_path, bundle_path = render_reading_report(
        run_dir / "06-reading-report" / "reading_report_spec.json",
        run_dir / "01-ingestion" / "paper_ir.json",
        run_dir / "06-reading-report",
        export_pdf=not args.no_pdf,
    )
    print(html_path)
    print(bundle_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
