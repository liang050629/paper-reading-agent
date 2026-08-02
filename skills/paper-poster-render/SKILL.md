---
name: paper-poster-render
description: Render an AMP-style research poster specification into deterministic local HTML and optional PNG/PDF browser exports, preserving original paper images and equation crops with a guarded LaTeX fallback. Use when a validated poster plan needs layout, asset copying, formula display, print sizing, or browser rendering.
---

# Paper Poster Render

Render only from `poster_spec.json`; do not invent scientific content.

## Rules

1. Use the bundled clean-room AMP-style template.
2. Copy only selected local paper assets into the run directory.
3. Remove page headers and continuous white margins from the overview crop,
   then preserve aspect ratio with `object-fit: contain` while filling the
   available overview region.
4. Prefer a high-resolution equation crop in deterministic offline exports.
   Use a pinned local math renderer when an equation has only LaTeX. Never
   expose raw display-math delimiters in the poster.
5. When an overview figure is absent, render the validated
   `sourced_method_flow` at full panel size. Expose overview mode, stage count,
   and empty-state metrics. A disclaimer is not a valid overview.
6. Export a 16:9 HTML canvas, PNG, and 48×27-inch PDF.
7. Record DOM metrics during browser export.
8. Render a bottom-right Project panel. Show a verified code URL when present;
   otherwise display `Code not publicly available`.
9. Render `experimental_results_spec.json` exactly: one primary quantitative
   asset, zero or one supporting asset, the verified metric cards available,
   and its selected adaptive layout. Preserve original crops with `object-fit:
   contain`; never redraw experimental data. Render `verified_focus_table`
   cells as a crisp HTML table with the proposed row, baselines, and source
   context intact.
10. Render the Method visual mode exactly as planned. For `single_overview`,
    show the overview once and use a numbered reading path below. For
    storyboards, preserve original images and connect adjacent module cards.
11. Keep Experimental Design visually secondary to the method explanation.
12. Render the Key Idea type from `key_idea_spec.json`. Do not reserve an
    equation slot when `display_mode` is `none`; expand the contrast,
    mechanism, architecture, or finding visual instead.
    Choose one-item, two-item, three-step, or grid geometry from the validated
    `visual_type`; never keep a three-step grid for a single item.
13. Preserve original equation-crop aspect ratio and expose its ID and display
    mode to browser metrics.
14. Expose the result layout, asset IDs/roles, metric count, natural
    resolution, rendered size, object-fit mode, image scale, focus-table
    minimum font, and horizontal overflow to browser metrics. Do not upscale
    or shrink an unreadable table to repair layout.
15. Render Motivation and Contributions only from each item's `visible_text`.
    Never read or expose `raw_statement`, source records, citation metadata, or
    rejected candidates. Adapt columns, wrapping, and card density to the
    validated item count without dropping items.
16. Render Method cards from their validated display mode. Show
    `original_figure` as the paper asset plus one explanation. Show
    `mechanism_flow` as a compact HTML mechanism/purpose flow; never stretch a
    text-only card into an image-sized empty box. Dense method panels may
    reduce non-empty text fallback cards to preserve readability; empty cards
    remain invalid. If an original asset cannot load, use its bundled
    evidence-backed flow as the visual fallback.
17. In the full pipeline, render first to `poster-candidate.*`. Promote it to
    `poster.*` only after final QA passes. Preserve a blocked candidate as
    `poster-debug.*` with invalid-preview metadata; never present it as the
    formal deliverable.

Read [runtime.md](references/runtime.md) before changing Playwright or browser
discovery. The Node script uses an argument array and never executes a shell
string.

```powershell
python scripts/run.py --spec poster_spec.json --paper-ir paper_ir.json --output runs/paper/04-poster
```
