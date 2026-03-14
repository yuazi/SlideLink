# SlideLink

`SlideLink` is a domain-agnostic tool that contextually aligns markdown lecture notes with corresponding course slides (PDF) using TF-IDF semantic similarity and visual analysis.

## Why use this?

*   **Medicine:** Automatically link dense clinical notes to anatomical diagrams and radiographic images from lecture slides.
*   **Psychology:** Match case study discussions in your notes to the relevant experimental data visualizations in the course presentation.
*   **STEM:** Bridge the gap between LaTeX-heavy derivations in your notes and the step-by-step algorithmic visualizations in course slides.

## Getting Started

This repository is "ready-to-go" with the default directory structure already created.

### 1. Installation

Clone the repository and install the package in editable mode:

```bash
git clone https://github.com/yuazi/SlideLink.git
cd SlideLink
pip install -e .
```

### 2. Add your Files

Copy your files into the pre-created folders:

1.  **Notes:** Put your `.md` files in the `notes/` directory.
2.  **Slides:** Put your `.pdf` lecture slides in the `notes/pdfs/` directory.

> **Tip:** Ensure your note filename matches your slide filename (e.g., `01_Intro.md` and `01_Intro.pdf`) for the best automatic matching.

### 3. Run the Tool

Simply run the command from the root directory:

```bash
slidelink-run
```

The tool will analyze your notes, find the best matching slides, extract them as images into the `assets/` folder, and insert the links directly into your markdown files.

## CLI Reference

| Argument | Default | Description |
| :--- | :--- | :--- |
| `--note` | None | Single markdown note to process. |
| `--notes-dir` | `notes` | Directory containing markdown notes. |
| `--pdf-dir` | `notes/pdfs` | Directory containing course slides (PDF). |
| `--asset-dir` | `assets` | Target asset root for extracted images. |
| `--min-score` | `0.33` | Minimum confidence score required for a match. |
| `--subject-label` | `Lecture` | Prefix used for image filenames and logs. |
| `--aliases-file` | None | Path to a JSON file mapping LaTeX commands to alias sets. |
| `--headings-config` | None | Path to a JSON file with 'skip' and 'generic' heading lists. |
| `--dry-run` | False | Log proposed changes without editing files. |

## Customizing for your subject

### LaTeX Aliases

If you are in a STEM field, you can provide a JSON file mapping LaTeX commands to plain-text aliases to improve matching for mathematical concepts:

```json
{
    "\\nabla": ["nabla", "gradient", "grad"],
    "\\sigma": ["sigma", "sigmoid", "standard deviation"]
}
```

Usage: `slidelink-run --aliases-file examples/aliases_stem.json`

### Heading Configuration

Override which headings are skipped or treated as "generic" (requiring higher confidence) by providing a config file:

```json
{
    "skip": ["introduction", "further reading"],
    "generic": ["overview", "results"]
}
```

Usage: `slidelink-run --headings-config examples/headings_config.json`

## Contributing

Suggestions and bug reports are welcome! Please open a GitHub issue to discuss any changes.

---
License: MIT
