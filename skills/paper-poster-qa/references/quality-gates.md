# Quality gates

Route failures as follows:

| Code family | Responsible stage |
|---|---|
| `PARSE_`, page/caption mismatch | `paper-ingest` |
| `STORY_` | `paper-storyline` |
| `METHOD_GRAPH_` | `paper-method-graph` |
| `METHOD_ASSET_`, `METHOD_CONTAINS_`, caption-content mismatch | `paper-method-figure-map` |
| `METHOD_MODULE_`, `METHOD_OVERVIEW_` | `paper-method-visual-compose` |
| `KEY_IDEA_` | `paper-key-idea` or `paper-poster-render` when explicitly a render mismatch |
| Motivation/Contribution copy, cleanup, role, merge, completeness, or provenance checks | `paper-motivation-contributions` |
| `RESULT_` content/provenance/metric/layout/glyph crop safety | `paper-experimental-results` |
| `RESULT_` wrong or source-unreadable asset | `paper-asset-select` |
| `RESULT_` Poster-size unreadable asset | `paper-poster-compose` |
| `RESULT_` stretch/render mismatch | `paper-poster-render` |
| unsupported or conflicting claim | `paper-evidence-audit` |
| `ASSET_CAPTIONS_`, wrong overview | `paper-asset-select` |
| `CONTENT_`, density | `paper-poster-compose` |
| `OVERFLOW_`, `OVERLAP_`, `RENDER_` | `paper-poster-render` |

Use three delivery tiers:

- `passed`: no blocking errors or warnings;
- `usable_with_warnings`: evidence remains truthful and readable, but an
  optional panel is sparse or a presentation preference is imperfect;
- `blocked`: truthfulness, source binding, figure role, exact numeric safety,
  visible-language integrity, or core readability is unsafe.

Never downgrade numeric mismatches, missing baselines, Method/Result role
conflicts, missing assets, raw LaTeX, incomplete sentences, core truncation,
unreadable tables, or major overlap. Sparse metric count, mixed-but-truthful
result contexts, missing large-table focus crops, and non-empty adaptive
Method fallback-card reduction are warnings. Preserve blocked renders only as
debug artifacts.

