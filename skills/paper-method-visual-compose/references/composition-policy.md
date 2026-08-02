# Method visual composition policy

Preserve original figures and aspect ratios. Do not regenerate scientific
diagrams.

For a complete overview, render the image once at large scale and add a sourced
reading path. For overview plus details, add only figures that cover previously
uncovered modules. For a storyboard, order original method figures by the
method graph and connect adjacent cards visually.

For each module card, prefer a usable original figure plus one short
explanation. If no reliable dedicated figure exists, emit a compact
`mechanism_flow` card with sourced mechanism and purpose stages. If a planned
image is unavailable at render time, degrade to the same flow card instead of
showing an empty or dashed image region.

When several captions say "overall", prefer the figure aligned with the method
variant adopted in the main experiments or conclusion. Treat earlier/static/
auxiliary variants as details. Do not use document order to break a semantic
tie.

A complete overview may still be followed by dedicated module figures when
their captions map cleanly to distinct method nodes. This is elaboration, not
duplicate rendering: keep the whole network above and the module diagrams
below.

Require at least 67% module coverage. Require zero result-role figures in the
Method area. Keep dataset, baseline, metric, and protocol facts in a compact
experimental-design strip.
