---
name: paper-method-visual-compose
description: Compose a reader-first visual explanation of a paper method from a sourced method graph and classified original figures. Use when deciding between a single complete overview, overview plus necessary detail figures, or a multi-figure storyboard with arrows and short module explanations.
---

# Paper Method Visual Compose

Choose the smallest set of original visuals that explains the method.

## Decision

1. Use `single_overview` only when the canonical whole figure covers all
   sourced method modules. Do not repeat it as thumbnails.
2. Use `overview_plus_details` when the overview needs a small number of
   non-redundant module or variant figures. Keep the canonical main-method
   figure in Method Overview and place auxiliary variants below. Also use this
   mode when a complete overview has dedicated, caption-grounded module figures
   that materially improve blind reading.
3. Use `multi_figure_storyboard` when no complete overview exists.
4. Use `text_only_method_path` only when no eligible method figure exists.
5. Emit every Method card with exactly one display mode:
   `original_figure` when a reliable module asset exists, otherwise
   `mechanism_flow`. Build the fallback from sourced Method-node text and keep
   it compact; never create an empty image placeholder.

Order callouts and arrows by `method_graph.json`. Keep descriptions short and
source-grounded. Allocate experimental setup to a secondary strip and never
place result figures or result numbers there.

## Reader check

After browser rendering, inspect the Method Overview and Method & Experimental
Design panels without consulting the paper text. Require the reviewing agent to
identify:

1. the method's core modules;
2. their reading order or explicitly non-causal exposition order;
3. the purpose of each module;
4. the main innovation points;
5. whether any result figure entered the Method area.

Return unclear modules to method graph or visual composition. A clean DOM is
not sufficient when the visual explanation cannot be understood by a new
reader.

Read [composition-policy.md](references/composition-policy.md) for coverage and
redundancy rules.

```powershell
python scripts/run.py --paper-ir paper_ir.json --method-graph method_graph.json --figure-map method_figure_map.json --output runs/paper/04-poster
```
