---
name: paper-reading-report-qa
description: Validate a generated paper reading report for source traceability, Formula and Claim provenance, Poster coverage, missing assets, unreadable typography, horizontal overflow, and required HTML/Markdown/PDF outputs. Use before accepting or publishing any reading report.
---

# Paper Reading Report QA

Block a reading report that looks complete but cannot be traced back to the
paper.

## Required checks

1. Every asserted storyline, Motivation, Contribution, and method module has a
   source block.
2. Every referenced block exists in `source_index.json`.
3. Every equation has page, bbox, and either an original image or LaTeX.
4. Every supported Claim has linked evidence and retains caveats.
5. Every Poster item has a report coverage mapping.
6. HTML and Markdown exist; PDF exists when browser export was requested.
7. Browser metrics contain no missing image, uncontrolled horizontal overflow,
   or sub-10-pixel text.
8. Inferred content remains visibly labeled.

Return semantic failures to `paper-reading-report-compose` and rendering
failures to `paper-reading-report-render`. Read
[qa-policy.md](references/qa-policy.md) before changing a blocking rule.

## Run

```powershell
python scripts/run.py --run-dir D:\path\to\completed-poster-run
```
