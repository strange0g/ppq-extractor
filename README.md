# Past Paper Question (PPQ) Extractor

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![Tooling: uv](https://img.shields.io/badge/tooling-uv-purple.svg)](https://docs.astral.sh/uv/)
[![Linting: ruff](https://img.shields.io/badge/linter-ruff-orange.svg)](https://docs.astral.sh/ruff/)

An autonomous extraction and verification system for extracting Cambridge A-Level Mathematics past paper questions from PDF format into structured, reusable image and metadata assets.

---

## Overview

Past paper question preparation traditionally requires laborious manual cropping of examination booklets. Cambridge examination papers contain shared question stems (diagrams and preambles), multiple question parts, and extensive candidate writing workspace lines that inflate image sizes and create redundancy.

**PPQ Extractor** solves this by establishing a decoupled, autonomous extraction and audit pipeline:
- **Two-Tier Question Packages**: Shared preambles are extracted once into a standalone Question Preamble Image (`preamble.png`), while Question Parts are cropped into isolated Question Part Images (`part_{label}.png`) without visual redundancy.
- **Composite Question Images**: Stitched question overviews (`full.png`) unite preamble and parts while excising candidate handwriting answer workspaces.
- **Machine-Readable Taxonomy**: Atomic `question.json` metadata descriptors and paper-level `manifest.json` indices track mark allocations, slice coordinates, context dependencies, and official Cambridge Syllabus Topic Codes (e.g. `1.1 Quadratics`, `1.7 Differentiation`).
- **Autonomous Agent Verification**: Two decoupled autonomous agent roles—**Extractor Agent** and **Verifier Agent**—operate asynchronously via a local Processing Queue (`.pipeline/queue.json`).
- **Automatic Margin Trimming**: Outer margin artifacts such as vertical *"DO NOT WRITE IN THIS MARGIN"* warnings are automatically detected and trimmed without clipping mathematical notation or mark brackets.

---

## Directory Structure

```
ppq-extractor/
├── data/
│   └── syllabus/              # Cambridge syllabus registries (e.g. 9709.json)
├── docs/
│   ├── adr/                   # Architectural Decision Records (ADRs)
│   ├── architecture.md        # Deep-dive system architecture documentation
│   └── development.md         # Developer guide, CLI usage, and test suite details
├── prompts/                   # Vision and agent system prompt specifications
├── scripts/
│   └── check.sh               # CI / pre-commit verification suite (ruff & unittest)
├── tests/                     # Deterministic unit and end-to-end pipeline test suite
├── tools/                     # Core deterministic CLI utilities and pipeline modules
│   ├── crop_slices.py         # Full-width slicing, stitching, and package generator
│   ├── pdf_to_images.py       # High-speed PDF page rendering utility
│   ├── pdf_utils.py           # Robust PDF page count and binary inspection helpers
│   └── queue_manager.py       # Master Processing Queue ledger manager
├── AGENTS.md                  # Autonomous agent instructions and operational rules
├── CONTRIBUTING.md            # Contributor guidelines and workflow
├── GLOSSARY.md                # Canonical domain language and terminology
├── pyproject.toml             # PEP 621 project configuration and tool settings
└── uv.lock                    # Deterministic dependency lockfile
```

---

## Quick Start

### Prerequisites

- **Python**: `>=3.10`
- **uv**: Fast Python package manager ([installation instructions](https://docs.astral.sh/uv/getting-started/installation/))
- **poppler-utils**: System library providing `pdftoppm` and `pdfinfo` for PDF rendering.
  - Ubuntu/Debian: `sudo apt-get install -y poppler-utils`
  - Arch/Fedora: `sudo dnf install poppler-utils` / `sudo pacman -S poppler`
  - macOS: `brew install poppler`

### Installation

Clone the repository and set up your virtual environment with `uv`:

```bash
git clone https://github.com/strange0g/ppq-extractor.git
cd ppq-extractor

# Synchronize dependencies and create virtual environment
uv sync
```

### Running Automated Checks

Verify that your environment, linting rules, and tests pass:

```bash
./scripts/check.sh
```

---

## Command-Line Tools

The repository installs three primary console entry points:

### 1. Queue Manager (`ppq-queue`)

Manages the file-based Processing Queue (`.pipeline/queue.json`):

```bash
# Scan a directory to discover Question Paper PDFs and update queue ledger
uv run ppq-queue scan --source-dir 9709/2024

# Poll next paper candidate for an agent role
uv run ppq-queue next --role extractor

# Display status of a specific paper
uv run ppq-queue show --id 9709_w24_qp_11

# Print concise queue summary table
uv run ppq-queue summary
```

### 2. High-Speed PDF Rendering (`ppq-render`)

Renders a Cambridge Question Paper PDF into high-resolution PNG page images:

```bash
uv run ppq-render --pdf 9709/2024/2024\ Nov/9709_w24_qp_11.pdf --out-dir data/output/9709_w24_qp_11/pages --dpi 200
```

### 3. Slicing & Question Package Generator (`ppq-crop`)

Executes full-width vertical cropping and composite stitching from a verified `manifest.json`:

```bash
uv run ppq-crop --manifest data/output/9709_w24_qp_11/manifest.json --pages-dir data/output/9709_w24_qp_11/pages --out-dir data/output/9709_w24_qp_11
```

Generated Question Packages are saved under `questions/q{NN}/`:
- `preamble.png`: Optional isolated Question Preamble Image
- `part_{label}.png`: Isolated Question Part Images
- `full.png`: Stitched Composite Question Image (answer workspaces excised)
- `question.json`: Atomic item descriptor with marks and taxonomy metadata

---

## Documentation

For further technical reading and contributor guidelines:
- [Architecture Guide](docs/architecture.md) — Pipeline lifecycle, coordinate spaces, and package layout.
- [Development Guide](docs/development.md) — Local development, test suites, and formatting workflows.
- [Contributing Guidelines](CONTRIBUTING.md) — Contribution process, coding standards, and commit conventions.
- [Domain Glossary](GLOSSARY.md) — Authoritative vocabulary for Question Packages, components, and queue states.
- [Architectural Decision Records](docs/adr/) — Technical decisions and design rationale.

---

## License

Internal proprietary research and educational tooling.
