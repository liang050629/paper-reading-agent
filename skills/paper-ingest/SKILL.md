---
name: paper-ingest
description: Parse research PDFs with MinerU's official cloud Extract client, or validate an existing PaperIR, into traceable text blocks, figures, equations, tables, captions, page numbers, coordinates, and parser diagnostics. Use before paper analysis whenever source fidelity, single- or multi-column reading order, original figures, formula extraction, or provenance is required.
---

# Paper Ingest

Create the canonical `PaperIR` used by every downstream skill.

## Parser policy

1. Send every PDF through the official `mineru-open-api extract` client.
2. Use the `vlm` model by default for complex academic layouts. Use `pipeline`
   when zero-hallucination extraction is more important than maximum layout
   accuracy.
3. Allow an existing PaperIR JSON to pass through validation without invoking
   MinerU.
4. Fail closed when the cloud client, authentication, upload, extraction,
   content list, or readable body text is missing or invalid.
5. Never fall back silently to pypdf, pdfplumber, a remote service, or another
   document parser.

Read [parser-adapters.md](references/parser-adapters.md) before invoking MinerU.
The source paper is transmitted to `mineru.net` for server-side extraction.
Do not send a confidential paper unless the user has authorized that upload.

## Required output

Write `paper_ir.json`, extracted local assets, and `parse_report.json`. Give
every block and asset a stable ID, page number, section, source parser, and
bounding box when available. Preserve the original image before creating any
crop.

Inspect every figure and table caption. Do not assume Figure 1 is the overview.
Prefer MinerU LaTeX for an equation; when reliable LaTeX is unavailable, retain
the equation bounding box and create a page crop marked `page_crop` in
provenance. Apply the same crop fallback when a figure has coordinates but its
extracted file is missing.

Do not invent or silently drop a page, caption, formula, table, or asset.
Record every failure in `parse_report.json`.

## Cloud client and authentication

Install the official lightweight client when `mineru-open-api` is unavailable:

```powershell
npm install --prefix .tools mineru-open-api
```

This installs only the cloud API client, not MinerU models or a local inference
runtime. Ask before installing. The adapter discovers the project-private
wrapper automatically; a global installation is also supported. Create a token
at <https://mineru.net/apiManage/token>, then configure it interactively:

```powershell
.\.tools\node_modules\.bin\mineru-open-api.cmd auth
.\.tools\node_modules\.bin\mineru-open-api.cmd auth --verify
```

Never place a token in a prompt, command argument, repository, report, or output
artifact. The client resolves credentials from `MINERU_TOKEN` or its user
configuration. Set `PAPERPOSTER_MINERU_CLI` only when the client is not on
`PATH`.

Optional controls:

- `PAPERPOSTER_MINERU_MODEL=vlm|pipeline`
- `PAPERPOSTER_MINERU_LANGUAGE=en|ch|...`
- `PAPERPOSTER_MINERU_TIMEOUT_SECONDS=900`

## Run

```powershell
python scripts/run.py --input paper.pdf --output runs/paper/01-ingestion
```

