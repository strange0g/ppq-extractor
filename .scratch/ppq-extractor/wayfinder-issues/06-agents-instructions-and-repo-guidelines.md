# Ticket 06: Autonomous Agent Repository Guidelines and AGENTS.md

Type: prototype
Status: resolved
Blocked by: 04, 05

## Question

How should `AGENTS.md` and root guidelines be authored so that any autonomous agent instantiated in the repository immediately detects its operational environment, understands the pipeline roles (Extractor vs. Verifier), executes the required CLI tools, adheres to `GLOSSARY.md`, and maintains atomic state commits?

## Answer

### 1. Structure of `AGENTS.md`

`AGENTS.md` at the repository root must establish:
1. **Pipeline Roles**: Clear distinction between the Extractor Agent (discovers unprocessed papers, converts pages, detects bounding slices, generates crops/manifest) and the Verifier Agent (audits extracted crops, validates mark sums, fixes discrepancies, approves papers).
2. **Domain Grounding**: Explicit instruction that all agents must read and adhere to [`GLOSSARY.md`](file:///home/raied/Programming/ppq-extractor/GLOSSARY.md) for terminology (e.g., Question Part Image vs Composite Question Image, Full-Width Crop, Answer Workspace).
3. **Queue Discipline**:
   - Always query `.pipeline/queue.json`.
   - Never overwrite in-progress records.
   - Extractor must prioritize `needs_rework` before `unprocessed`.
4. **Deterministic Tooling Mandate**:
   - Do not write throwaway scripts or reinvent image rendering.
   - Always use `python3 -m tools.pdf_to_images` and `python3 -m tools.crop_slices`.
5. **Git Protocol**:
   - Every agent session must commit its changes atomically with standard prefix: `feat(extractor): extract <id>` or `feat(verifier): verify <id>`.

### 2. Prompt Storage Convention

To ensure the autonomous scheduler can inject exact prompt files cleanly, prompts are stored as version-controlled Markdown files under `prompts/`:
- `prompts/extractor_agent.md`: The outer system instructions for an Extractor Agent session.
- `prompts/verifier_agent.md`: The outer system instructions for a Verifier Agent session.
- `prompts/vision_slicing.md`: The inner multimodal vision prompt template for extracting $0–1000$ coordinates.

