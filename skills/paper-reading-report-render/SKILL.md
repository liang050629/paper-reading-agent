---
name: paper-reading-report-render
description: Render a reading_report_spec.json into a navigable HTML report, portable Markdown notes, and an A4 PDF while copying original paper figures, equations, and result assets. Use after paper-reading-report-compose or when reading-report outputs need regeneration without rerunning paper analysis.
---

# Paper Reading Report Render

Render the detailed reading artifact without changing its factual content.
Original paper assets take priority over AI redraws.

## Workflow

1. Read `reading_report_spec.json` and the original `paper_ir.json`.
2. Copy referenced figures, equations, and result assets into
   `06-reading-report/assets/`.
3. Render `reading_report.html` with stable source anchors.
4. Render `reading_report.md` for portable notes and version control.
5. Use Playwright to export an A4 `reading_report.pdf`.
6. Persist `reading_report_render_bundle.json` and render metrics.

## Layout rules

- The report may span multiple pages; do not compress it into a Poster canvas.
- Keep body text readable at A4 size.
- Preserve figure aspect ratios and table comparison context.
- Allow tables to scroll in HTML, but avoid print overflow.
- Display page, section, and block links next to the statements they support.
- Do not expose hidden raw pipeline fields unless they are part of the source
  index.

Read [render-policy.md](references/render-policy.md) before editing the
template or browser export.

## Run

```powershell
python scripts/run.py --run-dir D:\path\to\completed-poster-run
```
