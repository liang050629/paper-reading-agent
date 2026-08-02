# Browser runtime

The renderer searches, in order:

- `PAPER_READER_NODE`;
- `node` on PATH;
- the bundled Codex Node runtime.

It similarly checks `PAPER_READER_NODE_MODULES` for Playwright and
`PAPER_READER_BROWSER` for a Chromium executable. Declare Playwright in the
deployment environment instead of relying on Codex-specific paths.

Browser export opens only the generated local HTML file. Keep all poster
images local. If MathJax is later vendored, pin its version and include it as a
local template asset. Until then, render the original high-resolution equation
crop instead of placing raw LaTeX in HTML.
