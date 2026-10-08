# 04: Autonomous Prompts Suite & AGENTS.md Guidelines

**What to build:** The complete, version-controlled system prompts in `prompts/` and root `AGENTS.md` establishing autonomous runner rules, domain terminology enforcement from `GLOSSARY.md`, CLI tool commands, and git commit conventions.

**Blocked by:** 02: Full-Width Slicing and Composite Stitching Tool, 03: Master Queue Ledger & Pipeline Manager

**Status:** claimed

- [ ] `prompts/extractor_agent.md` contains complete instructions for polling the queue, running `tools.pdf_to_images`, prompting the vision LLM, invoking `tools.crop_slices`, assembling `manifest.json`, and committing git state.
- [ ] `prompts/vision_slicing.md` specifies the normalized $[ymin, 0, ymax, 1000]$ coordinate schema, strictly excises dotted answer lines, and isolates stem preambles from subparts.
- [ ] `prompts/verifier_agent.md` contains instructions for polling `extracted` papers, verifying mark-sum invariants, conducting page-by-page visual audits, autonomously repairing coordinates, and approving/flagging status.
- [ ] Root `AGENTS.md` is updated with pipeline operational guidelines, tool command references, and strict adherence to `GLOSSARY.md`.
