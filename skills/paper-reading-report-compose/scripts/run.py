from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from paperposter.reading_report import compose_reading_report  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Compose a sourced reading report.")
    parser.add_argument("--run-dir", required=True, type=Path)
    args = parser.parse_args()
    run_dir = args.run_dir.resolve()
    spec, source_index = compose_reading_report(
        run_dir / "01-ingestion" / "paper_ir.json",
        run_dir / "02-analysis" / "paper_story.json",
        run_dir / "02-analysis" / "claim_evidence.json",
        run_dir / "02-analysis" / "method_graph.json",
        run_dir / "03-assets" / "asset_catalog.json",
        run_dir / "03-assets" / "selected_assets.json",
        run_dir / "03-assets" / "method_figure_map.json",
        run_dir / "04-poster" / "method_visual_plan.json",
        run_dir / "04-poster" / "key_idea_spec.json",
        run_dir / "04-poster" / "experimental_results_spec.json",
        run_dir / "04-poster" / "highlights_spec.json",
        run_dir / "04-poster" / "motivation_spec.json",
        run_dir / "04-poster" / "contribution_spec.json",
        run_dir / "04-poster" / "poster_spec.json",
        run_dir / "06-reading-report",
    )
    print(spec)
    print(source_index)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
