# Third-party references

The project implementation is a clean-room composition. The production MinerU
integration uses OpenDataLab's official `mineru-open-api` cloud client through
`paper-ingest`.

| Component | Upstream | Use in this project |
|---|---|---|
| Skill authoring | https://github.com/anthropics/skills/tree/main/skills/skill-creator | Skill structure, progressive disclosure, validation workflow |
| Paper analysis | https://github.com/bytedance/deer-flow/tree/main/skills/public/academic-paper-review | Review phases and evidence-grounded analysis concepts |
| Critical review | https://github.com/K-Dense-AI/scientific-agent-skills/tree/main/scientific-skills/peer-review | Methodology and claim-evidence audit concepts only |
| Critical thinking | https://github.com/K-Dense-AI/scientific-agent-skills/tree/main/scientific-skills/scientific-critical-thinking | Bias, confound, causal, and overclaim checks |
| HTML poster guidance | https://github.com/K-Dense-AI/scientific-agent-skills/tree/main/scientific-skills/pptx-posters | Font, content-density, overflow, and browser-export guidance |
| Poster pipeline/evaluation | https://github.com/Paper2Poster/Paper2Poster | Asset library, visual feedback loop, PaperQuiz, and VLM-judge concepts |
| Visual reference | https://github.com/visresearch/AMP/blob/main/docs/poster.png | Layout proportions and visual hierarchy only |
| MinerU cloud Skill | https://github.com/opendatalab/MinerU-Ecosystem/blob/main/skills/SKILL.md | Authentication, client invocation, model selection, and output behavior |
| MinerU cloud client | https://github.com/opendatalab/MinerU-Ecosystem/tree/main/cli/mineru-open-api | Required lightweight external client; parsing runs on MinerU servers |
| Parser comparison references | https://github.com/docling-project/docling, https://github.com/kermitt2/grobid, https://github.com/datalab-to/marker | Future offline comparison only; never invoked automatically |
| Browser rendering | https://github.com/microsoft/playwright | Optional HTML screenshot and PDF export |

Review every upstream license before bundling or redistributing code. MinerU
Ecosystem is Apache-2.0. Marker is GPL-3.0, and individual K-Dense skills may
have licenses that differ from their parent repository.
