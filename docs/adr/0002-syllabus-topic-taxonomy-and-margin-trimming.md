# Syllabus Topic Taxonomy and Automatic Margin Trimming

We introduce a canonical machine-readable syllabus topic registry (`data/syllabus/9709.json`) linking Question Packages to Cambridge syllabus section codes (e.g. `1.1 Quadratics`, `1.7 Differentiation`), and implement automatic lateral margin trimming in `tools.crop_slices` to eliminate vertical `DO NOT WRITE IN THIS MARGIN` markings introduced in recent examination papers without manual pixel coordinates.

## Context & Problem

1. **Topic-Wise Question Banking**: Downstream applications require grouping questions and parts by syllabus topic. Storing full topic titles repetitively across thousands of crops invites typos and divergence. Standard Cambridge syllabus topics follow hierarchical dot notation (`<paper>.<topic>`, e.g., `1.1`, `1.2`, `1.7`).
2. **Margin Warning Artifacts**: Recent Cambridge write-in examination papers (notably starting around 2024 revisions) feature vertical margin bars (`DO NOT WRITE IN THIS MARGIN`) on the outer edges (right side on even pages, left side on odd pages). Because the extractor uses full-width horizontal slicing (0..1000 normalized), these warnings appear in the stitched images unless trimmed.

## Decision

1. **Master Syllabus Registry**: Store the official Cambridge AS & A Level Mathematics taxonomy in `data/syllabus/9709.json` mapping two-level codes (`code: "1.1"`, `title: "Quadratics"`) by component (`1` through `6`).
2. **Metadata Attribution**: Question Packages record topic codes in `question.json` at the part level (`parts[i].topics: ["1.7"]`) and aggregated at the question level (`topics: ["1.7", "1.8"]`).
3. **Automatic Margin Trimming**: `tools.crop_slices` automatically inspects page images for vertical margin text or bar lines. When present, it automatically trims the outer lateral margin without clipping any mathematical text, diagrams, or mark brackets `[X]`. Agents retain the standardized full-width 0..1000 vertical coordinate space without computing margin offsets.

## Consequences

- Questions and isolated parts can be queried, filtered, and assembled into topic-wise question banks using lightweight string codes.
- Stitched composite images (`full.png`) and part crops (`part_*.png`) remain pristine without distracting vertical margin warnings.
- The pipeline remains backward-compatible with older pre-2024 examination papers that do not feature margin warning bars.
