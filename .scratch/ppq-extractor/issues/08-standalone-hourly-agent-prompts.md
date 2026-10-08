# 08: Standalone Hourly Agent Prompts & Question Number Invariants

**What to build:** System prompts and slicing instructions are modernized for decoupled hourly autonomous agent execution in isolated environments (removing nested LLM loops). Vision slicing guidelines enforce that vertical bounds (`ymin`) strictly encompass question numbers with an upward buffer (fixing Question 1 number cutout), Extractor instructions govern Question Package generation, and Verifier instructions define the audit of Question Packages and atomic `question.json` metadata.

**Blocked by:** 07: Two-Tier Question Package Slicing Engine

**Status:** ready-for-agent

- [ ] `prompts/vision_slicing.md` mandates that `ymin` must start above top-level question numerals, including an upward safety buffer to prevent clipping question headings.
- [ ] `prompts/extractor_agent.md` defines the agent as the direct multimodal LLM operating in an isolated hourly run, performing layout analysis, invoking `tools.crop_slices` to generate Question Packages, and committing assets.
- [ ] `prompts/verifier_agent.md` defines the audit and self-repair procedures for the subsequent hourly run, checking mark sums, reconciling question numbers and subparts, validating `question.json` descriptors, and updating queue status.
- [ ] Unit tests in `tests/test_prompts_and_guidelines.md` or prompt integrity checks validate adherence to `GLOSSARY.md` and updated operational steps.
