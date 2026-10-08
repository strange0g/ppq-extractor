# Two-Tier Question Package and Decoupled Stem Architecture

We decouple shared question stems/preambles from individual Question Parts into an isolated two-tier Question Package format (`questions/q{NN}/`), storing `preamble.png`, isolated `part_*.png`, and composite `full.png` alongside an atomic `question.json` metadata descriptor, indexed by a paper-level `manifest.json`.

## Context & Problem

Previously, the extraction pipeline vertically concatenated the shared question preamble (diagrams and stem text) onto every individual subpart image (e.g. `q10_a.png`, `q10_b.png`). This caused 300–400% PNG storage bloat, visual token inflation in multimodal LLM contexts, and visual repetition in downstream interfaces. Furthermore, raw crops lacked item-level metadata and global paper provenance.

## Decision

1. **Decoupled Asset Slicing**: Shared preamble stems are cropped once into `preamble.png`. Question parts are cropped purely in isolation as `part_{label}.png` without prepending the preamble.
2. **Composite Preserved**: A unified `full.png` is generated per question, excising candidate answer workspaces.
3. **Atomic Question Packages**: Each question is encapsulated in `questions/q{NN}/` containing its image assets and an atomic `question.json` item descriptor declaring marks, slices, and context dependencies (`dependencies: ["preamble"]`).
4. **Paper-Level Manifest**: `manifest.json` at the paper root serves as the whole-paper ledger and verification audit record.

## Considered Options

- **Embedding Preamble in Every Subpart Crop (Rejected)**: Redundant image storage, visual clutter when displaying consecutive parts, and token waste in vision models.
- **Flat Asset Pool with Prefixes (`crops/{paper_id}_q01_a.png`) (Rejected)**: Weak encapsulation, fragile bash globbing, and lack of item-level metadata.

## Consequences

- Downstream frontends and AI agents can query individual question parts modularly while referencing the shared preamble only when needed.
- Multimodal prompt caching can cache `preamble.png` once across multi-turn interactions.
- Filesystem layout reflects the formal domain model defined in `GLOSSARY.md`.
