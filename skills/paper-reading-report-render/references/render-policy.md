# Reading report render policy

- Render a responsive long-form HTML document and an A4 print layout.
- Copy referenced original assets into the report bundle.
- Never stretch images or redraw experimental values.
- Use semantic headings and stable source anchors.
- Keep body text at least 10 px in browser metrics and readable in the A4 PDF.
- HTML tables may use a bounded scroll container. Print output must not overflow
  the A4 content box.
- Browser export records missing images, horizontal overflow, minimum font,
  source-link count, asset count, document height, and PDF page count.
