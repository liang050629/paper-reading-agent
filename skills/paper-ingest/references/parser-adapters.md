# MinerU cloud adapter

## Production route

Use MinerU as the only PDF semantic parser. Invoke the official
`mineru-open-api` client from `PATH` or `PAPERPOSTER_MINERU_CLI`. Request
Markdown and JSON together so the client also downloads extracted images:

```powershell
mineru-open-api extract paper.pdf -o raw -f md,json --model vlm
```

Keep the Markdown as a human-readable diagnostic artifact and use the JSON
content list as the PaperIR source of truth. Treat the upload, polling, and
download as one bounded extraction step.

## PaperIR mapping

- Convert `page_idx` from zero-based to one-based.
- Convert text with a positive heading level into headings; keep ordinary text
  as paragraphs.
- Convert equations from their text field into LaTeX after removing display
  delimiters.
- Convert image and chart items into figures and preserve their caption arrays.
- Convert table items into tables, preserving caption, HTML body, image, and
  coordinates when present.
- Attach `source_parser`, `source_item_index`, and `source_type` to each block
  and asset.
- Resolve every asset path inside the current MinerU raw directory before
  copying it. Reject path traversal.

Do not expose unstable MinerU IDs downstream. Generate stable PaperIR IDs from
captions and page-local order.

## Fail-closed checks

Stop ingestion when the client or token is missing, upload or polling fails,
the process times out or exits nonzero, the content list is missing or
ambiguous, JSON is invalid, or body text is empty. Write a failure report with
a bounded stdout/stderr tail. Do not substitute a basic parser and never record
the token.

Treat GROBID, Docling, and Marker only as future offline comparison
experiments. Never invoke them automatically. The user must know that this
route sends the source document to MinerU's cloud service.

