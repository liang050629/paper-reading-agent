# Paper Reading Agent

Turn research papers into evidence-grounded reading notes, visual posters, and
review-ready deliverable folders.

Paper Reading Agent is a local pipeline for reading academic PDFs with strict
source traceability. It extracts the paper into a normalized intermediate
representation, builds a claim-to-evidence graph, selects useful figures,
tables, and equations, then produces two human-facing outputs:

- a detailed reading report for careful study;
- an AMP-style poster for quick inspection and presentation.

It is designed as a reading assistant, not a citation-free summarizer. Every
major visible statement is tied back to paper sections, pages, blocks, captions,
or extracted visual assets.

## Highlights

- Evidence-grounded analysis: storyline, claims, evidence blocks, and asset
  provenance are kept as machine-readable JSON.
- Poster generation: creates a structured HTML poster with selected method,
  key idea, result, motivation, contribution, and highlight panels.
- Reading report generation: creates navigable notes in HTML, Markdown, and
  optionally PDF.
- Final deliverable packaging: copies the clean reader-facing files into a
  `00-final-deliverables/` folder after each run.
- Quality gates: checks visible text, layout overflow, missing assets, source
  provenance, and result readability before marking outputs as deliverable.
- PDF extraction through MinerU: supports complex academic PDFs through
  MinerU's official cloud extraction client.

## Output At A Glance

Each poster-mode run keeps the full intermediate pipeline and also creates a
compact handoff folder:

```text
00-final-deliverables/
|-- README.md
|-- manifest.json
|-- notes/
|   `-- reading-notes.md
|-- poster/
|   |-- poster.html
|   |-- poster.png
|   `-- poster.pdf
|-- reading-report/
|   |-- reading_report.html
|   |-- reading_report.md
|   `-- reading_report.pdf
`-- qa/
    |-- final_qa_report.json
    |-- reading_report_qa.json
    `-- pipeline_summary.json
```

The full run directory remains available for debugging, regression tests, and
machine-readable inspection. The `00-final-deliverables/` folder is the part
intended for readers, reviewers, or teachers.

## How It Works

```text
PDF or PaperIR
    |
    v
Ingestion and PaperIR normalization
    |
    v
Storyline, method graph, claim-evidence audit
    |
    v
Asset catalog and visual selection
    |
    +--> Reading report: HTML, Markdown, optional PDF
    |
    `--> Poster: HTML, optional PNG/PDF, QA report
              |
              v
       00-final-deliverables/
```

The pipeline does not assume that "Figure 1" is the overview figure. It reads
captions and surrounding context, classifies asset roles, and validates the
selected visual evidence before delivery.

## Requirements

Required:

- Python 3.10+
- Node.js and npm
- A MinerU account and API token
- `mineru-open-api`, MinerU's official cloud extraction client

Optional, for PNG/PDF browser exports:

- Microsoft Edge or Google Chrome
- Playwright available in a Node.js `node_modules` directory

Without browser export support, the pipeline can still produce HTML, Markdown,
JSON reports, and QA metadata.

## Installation

Install the Python package from the repository root:

```powershell
cd paper-reading-agent
python -m pip install -e .
```

For development and tests:

```powershell
python -m pip install -e ".[dev,validation]"
```

Install MinerU's official client:

```powershell
npm install --prefix .tools mineru-open-api
```

If you want PNG/PDF browser exports outside the Codex bundled runtime, also
install Playwright:

```powershell
npm install --prefix .tools playwright
$env:PAPER_READER_NODE_MODULES = (Resolve-Path .tools\node_modules)
```

Authenticate MinerU:

```powershell
.\.tools\node_modules\.bin\mineru-open-api.cmd auth
.\.tools\node_modules\.bin\mineru-open-api.cmd auth --verify
```

## Quick Start

Run the analysis-only pipeline:

```powershell
$env:PAPERPOSTER_MINERU_MODEL = "vlm"
$env:PAPERPOSTER_MINERU_LANGUAGE = "en"

paper-reader `
  --input paper.pdf `
  --output runs/paper-analysis `
  --mode analysis
```

Run the full poster and reading-report pipeline:

```powershell
paper-reader `
  --input paper.pdf `
  --output runs/paper-poster `
  --mode poster
```

Skip PNG/PDF browser export when you only need HTML, Markdown, and JSON:

```powershell
paper-reader `
  --input paper.pdf `
  --output runs/paper-poster `
  --mode poster `
  --no-browser-export
```

Regenerate the final deliverable package for an existing run:

```powershell
paper-deliverables `
  --summary runs/paper-poster/pipeline_summary.json
```

## Main Artifacts

Analysis mode creates:

- `paper_ir.json`: normalized document blocks, figures, tables, equations, and
  provenance;
- `paper_story.json`: sourced reading storyline;
- `claim_evidence.json`: claim-to-block evidence bindings;
- `method_graph.json`: method structure recovered from the paper;
- stage reports under `05-reports/`.

Poster mode additionally creates:

- `poster.html`, `poster.png`, and `poster.pdf`;
- `poster_spec.json`;
- `reading_report.html`, `reading_report.md`, and `reading_report.pdf`;
- `reading_report_spec.json` and `source_index.json`;
- `final_qa_report.json`;
- `00-final-deliverables/`.

## Quality Gates

The QA layer is intentionally evidence-focused. It blocks issues that would
make the output misleading, such as missing source assets, invalid evidence
IDs, broken image loads, severe layout overlap, or unsupported PDF parser
fallbacks.

Presentation sparsity is treated more gently. For example, a paper may still be
usable with warnings when it has fewer displayable motivation or contribution
items, a result table needs a better focus crop, or a selected result asset is
missing only a caption while its page and bounding box remain traceable.

## Privacy Notice

PDF ingestion uses MinerU's official cloud extraction client. When you run the
PDF path, the source document is transmitted to `mineru.net`.

Do not use this route for confidential, unpublished, or restricted papers
unless you have permission to upload them. Existing `PaperIR` JSON files can be
processed without calling MinerU.

## Repository Layout

```text
paper-reading-agent/
|-- src/paperposter/       # Python pipeline implementation
|-- skills/                # Codex skill wrappers and stage instructions
|-- schemas/               # JSON schemas for generated artifacts
|-- examples/              # Small local PaperIR example and assets
|-- tests/                 # Regression and contract tests
|-- tools/                 # Helper scripts
`-- pyproject.toml
```

## Development

Run the test suite:

```powershell
python -m pytest tests -q
```

Run a single pipeline test:

```powershell
python -m pytest tests/test_pipeline.py -q
```

## Project Status

This project currently includes:

- MinerU cloud-client ingestion;
- local PaperIR contracts;
- evidence-grounded analysis stages;
- poster generation and browser export;
- reading-report generation;
- final deliverable export;
- staged QA and regression tests.

No MinerU model runtime or paper dataset is bundled with this repository.

## License

MIT License. See [LICENSE](LICENSE).
