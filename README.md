<div align="center">

# SlideLink

**Contextually align your markdown lecture notes with the right slides — automatically.**

[![Python](https://img.shields.io/badge/python-3.8%2B-blue?logo=python&logoColor=white)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![CI](https://github.com/yuazi/SlideLink/actions/workflows/ci.yml/badge.svg)](https://github.com/yuazi/SlideLink/actions)

</div>

---

`SlideLink` is a domain-agnostic CLI tool that scans your markdown lecture notes and inserts the most relevant slide images directly into them. It uses **TF-IDF semantic similarity** and **visual analysis** to match note sections to PDF slides — no LLM required, no internet needed.

## Why use this?

| Field | Use Case |
|-------|----------|
| **Medicine** | Link dense clinical notes to anatomical diagrams and radiographic images |
| **Psychology** | Match case study discussions to experimental data visualizations |
| **STEM** | Bridge LaTeX-heavy derivations to step-by-step algorithmic slide visuals |
| **Any field** | Just drop in your `.md` notes and `.pdf` slides — it works out of the box |

## Getting Started

This repository is "ready-to-go" with the default directory structure already in place.

### 1. Installation

Clone the repository and install the package in editable mode:

```bash
git clone https://github.com/yuazi/SlideLink.git
cd SlideLink
pip install -e .
```

### 2. Add your Files

Copy your files into the pre-created folders:

- **Notes:** Put your `.md` files in the `notes/` directory.
- **Slides:** Put your `.pdf` lecture slides in the `notes/pdfs/` directory.

> **Tip:** Ensure your note filename matches your slide filename (e.g., `01_Intro.md` and `01_Intro.pdf`) for the best automatic matching.

### 3. Run the Tool

```bash
slidelink-run
```

SlideLink will analyze your notes, find the best matching slides, extract them as images into `notes/screenshots/`, and insert standard Markdown image links directly into your files.

### 4. Revert Changes

To remove all inserted screenshots and review comments and start fresh:

```bash
slidelink-revert --revert
```

## CLI Reference

| Argument | Default | Description |
|----------|---------|-------------|
| `--note` | None | Single markdown note to process. |
| `--notes-dir` | `notes` | Directory containing markdown notes. |
| `--pdf-dir` | `notes/pdfs` | Directory containing course slides (PDF). |
| `--asset-dir` | `notes/screenshots` | Target asset root for extracted images. |
| `--min-score` | `0.33` | Minimum confidence score required for a match. |
| `--subject-label` | `Lecture` | Prefix used for image filenames and logs. |
| `--aliases-file` | None | Path to a JSON file mapping LaTeX commands to alias sets. |
| `--headings-config` | None | Path to a JSON file with `skip` and `generic` heading lists. |
| `--dry-run` | `False` | Log proposed changes without editing files. |
| `--revert` | `False` | Remove inserted slidelink screenshots and review comments. |

## Customization

### LaTeX Aliases

For STEM fields, you can improve matching for mathematical concepts by providing a JSON file that maps LaTeX commands to plain-text aliases:

```json
{
  "\\nabla": ["nabla", "gradient", "grad"],
  "\\sigma": ["sigma", "sigmoid", "standard deviation"]
}
```

```bash
slidelink-run --aliases-file examples/aliases_stem.json
```

### Heading Configuration

Override which headings are skipped or treated as "generic" (requiring higher confidence):

```json
{
  "skip": ["introduction", "further reading"],
  "generic": ["overview", "results"]
}
```

```bash
slidelink-run --headings-config examples/headings_config.json
```

## Project Structure

```
SlideLink/
├── notes/              # Your markdown notes go here
│   ├── pdfs/           # Your PDF slides go here
│   └── screenshots/    # Auto-generated slide images (created by the tool)
├── slidelink/          # Core Python package
├── examples/           # Example alias and heading config files
├── scripts/            # Helper scripts
└── tests/              # Test suite
```

## Contributing

Suggestions and bug reports are welcome! Please [open a GitHub issue](https://github.com/yuazi/SlideLink/issues) to discuss any changes.

## License

Distributed under the [MIT License](LICENSE).
