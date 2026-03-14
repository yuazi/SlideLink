from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Iterable

try:
    import fitz  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - handled at runtime
    fitz = None

try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
except ImportError:  # pragma: no cover - handled at runtime
    TfidfVectorizer = None
    cosine_similarity = None


HEADING_RE = re.compile(r"^(#{2,6})\s+(.+?)\s*$")
IMAGE_RE = re.compile(r"!\[\[.*?\]\]|!\[.*?\]\(.*?\)")
LATEX_CMD_RE = re.compile(r"\\[A-Za-z]+(?:\{[^}]+\})?")
NON_WORD_RE = re.compile(r"[^a-z0-9]+")

DEFAULT_NOTES_DIR = Path("notes")
DEFAULT_PDF_DIR = DEFAULT_NOTES_DIR / "pdfs"
DEFAULT_ASSET_DIR = Path("assets")

# Default values for SKIP_HEADINGS and GENERIC_HEADINGS
DEFAULT_SKIP_HEADINGS = {
    "introduction",
    "summary",
    "references",
    "further reading",
}

DEFAULT_GENERIC_HEADINGS = {
    "algorithm",
    "algorithms",
    "alignment models",
    "architecture",
    "challenges",
    "key concepts",
    "key idea",
    "key properties",
    "methods overview",
    "motivation",
    "outputs",
    "overview",
    "papers",
    "representation learning models",
    "results",
    "techniques at a glance",
    "training data",
    "what is it",
}


@dataclass(frozen=True)
class SectionCandidate:
    note_path: Path
    heading_line: int
    heading_level: int
    heading_text: str
    parent_headings: tuple[str, ...]
    context_lines: tuple[str, ...]
    context_text: str
    math_terms: tuple[str, ...]
    concept_slug: str


@dataclass(frozen=True)
class SlideFeatures:
    page_number: int
    text: str
    normalized_text: str
    top_text: str
    image_count: int
    drawing_count: int
    visual_area_ratio: float
    visual_signal: float
    has_visuals: bool


@dataclass(frozen=True)
class SlideScore:
    slide: SlideFeatures
    total: float
    semantic: float
    title: float
    math_bonus: float
    visual_bonus: float


@dataclass(frozen=True)
class MatchDecision:
    candidate: SectionCandidate
    matches: tuple[SlideScore, ...]
    review_needed: bool


def require_runtime_dependencies() -> None:
    missing: list[str] = []
    if fitz is None:
        missing.append("PyMuPDF")
    if TfidfVectorizer is None or cosine_similarity is None:
        missing.append("scikit-learn")
    if missing:
        joined = ", ".join(missing)
        raise SystemExit(
            f"Missing required dependency/dependencies: {joined}. "
            "Install them with `python3 -m pip install PyMuPDF scikit-learn`."
        )


def normalize_text(value: str) -> str:
    value = value.lower()
    value = value.replace("’", "'")
    value = NON_WORD_RE.sub(" ", value)
    return " ".join(value.split())


def slugify(value: str, max_words: int = 6) -> str:
    words = re.findall(r"[A-Za-z0-9]+", value)
    if not words:
        return "Concept"
    clipped = words[:max_words]
    return "_".join(word.capitalize() for word in clipped)


def extract_lecture_number(path: Path) -> str | None:
    match = re.match(r"^(\d{1,2})", path.stem)
    if match:
        return match.group(1).zfill(2)
    return None


def is_substantive_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    if stripped in {"---", "***"}:
        return False
    if stripped.startswith("[[") and "Back to" in stripped:
        return False
    if IMAGE_RE.search(stripped):
        return False
    return True


def collect_context_lines(lines: list[str], start: int, end: int, limit: int = 5) -> list[str]:
    context: list[str] = []
    in_fence = False
    for idx in range(start, end):
        stripped = lines[idx].rstrip("\n")
        fence = stripped.strip().startswith("```")
        if fence:
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if not is_substantive_line(stripped):
            continue
        context.append(stripped.strip())
        if len(context) >= limit:
            break
    return context


def extract_math_terms(*parts: str) -> tuple[str, ...]:
    terms: set[str] = set()
    for part in parts:
        for token in LATEX_CMD_RE.findall(part):
            terms.add(token)
    return tuple(sorted(terms))


def expand_math_aliases(math_terms: Iterable[str], aliases: dict[str, set[str]]) -> set[str]:
    if not aliases:
        return set()
    expanded: set[str] = set()
    for term in math_terms:
        expanded.update(aliases.get(term, set()))
        stripped = term.lstrip("\\")
        stripped = stripped.split("{", 1)[0]
        if stripped:
            expanded.add(stripped.lower())
    return expanded


def is_generic_heading(candidate: SectionCandidate, generic_headings: set[str]) -> bool:
    normalized = normalize_text(candidate.heading_text)
    if normalized in generic_headings:
        return True
    # Very short headings tend to overfit slide titles without enough semantic support.
    return len(normalized.split()) <= 2 and normalized in {
        "architecture",
        "motivation",
        "results",
        "outputs",
        "overview",
        "papers",
    }


def parse_markdown_candidates(note_path: Path, skip_headings: set[str]) -> list[SectionCandidate]:
    lines = note_path.read_text(encoding="utf-8").splitlines()
    headings: list[tuple[int, int, str, tuple[str, ...]]] = []
    stack: list[tuple[int, str]] = []
    in_fence = False
    in_frontmatter = False

    for idx, raw_line in enumerate(lines):
        stripped = raw_line.strip()
        if idx == 0 and stripped == "---":
            in_frontmatter = True
            continue
        if in_frontmatter:
            if stripped == "---":
                in_frontmatter = False
            continue
        if stripped.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        match = HEADING_RE.match(raw_line)
        if not match:
            continue
        level = len(match.group(1))
        heading_text = match.group(2).strip()
        while stack and stack[-1][0] >= level:
            stack.pop()
        parents = tuple(text for _, text in stack)
        headings.append((idx, level, heading_text, parents))
        stack.append((level, heading_text))

    if not headings:
        return []

    candidates: list[SectionCandidate] = []
    for pos, (line_number, level, heading_text, parents) in enumerate(headings):
        next_heading_line = headings[pos + 1][0] if pos + 1 < len(headings) else len(lines)
        block = lines[line_number + 1 : next_heading_line]
        if any(IMAGE_RE.search(line) for line in block):
            continue
        normalized_heading = normalize_text(heading_text)
        if normalized_heading in skip_headings:
            continue
        context_lines = collect_context_lines(lines, line_number + 1, next_heading_line, limit=5)
        if not context_lines:
            continue
        body_words = len(normalize_text(" ".join(context_lines)).split())
        if body_words < 4 and level <= 2:
            continue
        repeated_heading = f"{heading_text} {heading_text}"
        parent_text = " ".join(parents)
        context_text = "\n".join(part for part in [parent_text, repeated_heading, *context_lines] if part)
        math_terms = extract_math_terms(heading_text, *context_lines)
        candidates.append(
            SectionCandidate(
                note_path=note_path,
                heading_line=line_number,
                heading_level=level,
                heading_text=heading_text,
                parent_headings=parents,
                context_lines=tuple(context_lines),
                context_text=context_text,
                math_terms=math_terms,
                concept_slug=slugify(heading_text),
            )
        )
    return candidates


def unique_area_sum(rects: Iterable[Any]) -> float:
    seen: set[tuple[float, float, float, float]] = set()
    total = 0.0
    for rect in rects:
        if rect is None:
            continue
        key = (
            round(rect.x0, 2),
            round(rect.y0, 2),
            round(rect.x1, 2),
            round(rect.y1, 2),
        )
        if key in seen:
            continue
        seen.add(key)
        total += max(rect.get_area(), 0.0)
    return total


def slide_has_meaningful_visuals(image_count: int, drawing_count: int, visual_area_ratio: float, text: str) -> bool:
    word_count = len(normalize_text(text).split())
    if image_count > 0:
        return True
    if drawing_count >= 6:
        return True
    if visual_area_ratio >= 0.018:
        return True
    if drawing_count >= 3 and visual_area_ratio >= 0.01 and word_count < 120:
        return True
    return False


def extract_slide_features(pdf_path: Path) -> tuple[Any, list[SlideFeatures]]:
    assert fitz is not None
    document = fitz.open(pdf_path)
    slides: list[SlideFeatures] = []

    for page_index in range(document.page_count):
        page = document.load_page(page_index)
        text = page.get_text("text")
        blocks = page.get_text("blocks")
        top_cutoff = page.rect.y0 + (page.rect.height * 0.15)
        top_text = " ".join(
            block[4].strip()
            for block in blocks
            if isinstance(block[4], str) and block[1] <= top_cutoff and block[4].strip()
        )

        drawings = page.get_drawings()
        image_rects = []
        for image in page.get_images(full=True):
            xref = image[0]
            try:
                image_rects.extend(page.get_image_rects(xref))
            except Exception:
                continue
        drawing_rects = [drawing.get("rect") for drawing in drawings if drawing.get("rect") is not None]
        page_area = max(page.rect.get_area(), 1.0)
        visual_area = unique_area_sum(image_rects) + unique_area_sum(drawing_rects)
        visual_area_ratio = min(visual_area / page_area, 1.0)
        image_count = len(image_rects)
        drawing_count = len(drawings)
        has_visuals = slide_has_meaningful_visuals(image_count, drawing_count, visual_area_ratio, text)
        visual_signal = min(1.0, (image_count * 0.35) + (drawing_count * 0.04) + (visual_area_ratio * 8.0))
        slides.append(
            SlideFeatures(
                page_number=page_index + 1,
                text=text,
                normalized_text=normalize_text(text),
                top_text=top_text,
                image_count=image_count,
                drawing_count=drawing_count,
                visual_area_ratio=visual_area_ratio,
                visual_signal=visual_signal,
                has_visuals=has_visuals,
            )
        )
    return document, slides


def title_similarity(candidate: SectionCandidate, slide: SlideFeatures) -> float:
    heading_text = normalize_text(candidate.heading_text)
    if not heading_text:
        return 0.0
    top_text = normalize_text(slide.top_text)
    if not top_text:
        return 0.0
    overlap = token_overlap_score(heading_text, top_text)
    fuzzy = SequenceMatcher(None, heading_text, top_text).ratio()
    contains = 1.0 if heading_text in top_text else 0.0
    return max(overlap, fuzzy * 0.8, contains)


def token_overlap_score(left: str, right: str) -> float:
    left_tokens = set(left.split())
    right_tokens = set(right.split())
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens)


def score_slides(
    candidates: list[SectionCandidate],
    slides: list[SlideFeatures],
    aliases: dict[str, set[str]],
    generic_headings: set[str],
) -> list[MatchDecision]:
    assert TfidfVectorizer is not None
    assert cosine_similarity is not None

    slide_texts = [slide.text or slide.top_text for slide in slides]
    vectorizer = TfidfVectorizer(stop_words="english", ngram_range=(1, 2))
    slide_matrix = vectorizer.fit_transform(slide_texts or [""])

    decisions: list[MatchDecision] = []
    for candidate in candidates:
        query = vectorizer.transform([candidate.context_text])
        semantic_scores = cosine_similarity(query, slide_matrix).ravel()
        math_aliases = expand_math_aliases(candidate.math_terms, aliases)
        ranked: list[SlideScore] = []

        for index, slide in enumerate(slides):
            if not slide.has_visuals:
                continue
            semantic = float(semantic_scores[index])
            title = title_similarity(candidate, slide)
            math_hits = 0
            if math_aliases:
                for alias in math_aliases:
                    if alias and alias.lower() in slide.normalized_text:
                        math_hits += 1
            math_bonus = 0.0
            if math_aliases:
                math_bonus = min(0.18, 0.18 * (math_hits / len(math_aliases)))
            visual_bonus = min(0.12, slide.visual_signal * 0.12)
            total = (semantic * 0.7) + (title * 0.18) + math_bonus + visual_bonus
            ranked.append(
                SlideScore(
                    slide=slide,
                    total=total,
                    semantic=semantic,
                    title=title,
                    math_bonus=math_bonus,
                    visual_bonus=visual_bonus,
                )
            )

        ranked.sort(key=lambda item: item.total, reverse=True)
        if not ranked:
            continue

        top_matches = ranked[:2]
        review_needed = False
        if len(top_matches) == 2:
            gap = top_matches[0].total - top_matches[1].total
            close_scores = gap <= 0.045
            generic_heading = is_generic_heading(candidate, generic_headings)
            score_floor = 0.52 if generic_heading else 0.45
            pair_confident = top_matches[0].total >= score_floor and top_matches[1].total >= (score_floor - 0.02)
            near_pages = abs(top_matches[0].slide.page_number - top_matches[1].slide.page_number) <= 4
            both_confident = pair_confident and near_pages
            review_needed = close_scores and both_confident

        decisions.append(
            MatchDecision(
                candidate=candidate,
                matches=tuple(top_matches if review_needed else top_matches[:1]),
                review_needed=review_needed,
            )
        )
    return decisions


def find_matching_pdf(note_path: Path, pdf_dir: Path) -> Path | None:
    direct_match = note_path.with_suffix(".pdf")
    if direct_match.exists():
        return direct_match

    lecture_number = extract_lecture_number(note_path)
    search_roots = [note_path.parent, pdf_dir]
    pdfs: list[Path] = []
    for root in search_roots:
        if root.exists():
            pdfs.extend(sorted(root.glob("*.pdf")))
    if lecture_number:
        by_number = [pdf for pdf in pdfs if lecture_number in pdf.stem]
        if len(by_number) == 1:
            return by_number[0]
        if len(by_number) > 1:
            note_tokens = set(normalize_text(note_path.stem).split())
            return max(by_number, key=lambda pdf: len(note_tokens & set(normalize_text(pdf.stem).split())))

    normalized_note = normalize_text(note_path.stem)
    for pdf in pdfs:
        if normalized_note and normalized_note in normalize_text(pdf.stem):
            return pdf
    return None


def image_filename(subject_label: str, lecture_number: str, page_number: int, concept_slug: str) -> str:
    return f"{subject_label}{lecture_number}_Pg{page_number:03d}_{concept_slug}.png"


def render_slide_image(document: Any, page_number: int, output_path: Path, dpi: int = 300) -> None:
    assert fitz is not None
    page = document.load_page(page_number - 1)
    zoom = dpi / 72.0
    matrix = fitz.Matrix(zoom, zoom)
    pixmap = page.get_pixmap(matrix=matrix, alpha=False)
    pixmap.save(output_path)


def insertion_snippet(
    decision: MatchDecision,
    lecture_number: str,
    subject_label: str,
    asset_dir: Path,
) -> tuple[list[str], list[Path]]:
    links: list[str] = []
    image_paths: list[Path] = []
    asset_folder = asset_dir / lecture_number
    for match in decision.matches:
        filename = image_filename(subject_label, lecture_number, match.slide.page_number, decision.candidate.concept_slug)
        image_paths.append(asset_folder / filename)
        links.append(f"![[{filename}]]")

    lines: list[str] = []
    if decision.review_needed and len(decision.matches) == 2:
        first, second = decision.matches
        lines.append(
            f"<!-- Review Needed: close slide match for '{decision.candidate.heading_text}' "
            f"(p{first.slide.page_number}: {first.total:.3f}, p{second.slide.page_number}: {second.total:.3f}) -->"
        )
    lines.extend(links)
    lines.append("")
    return lines, image_paths


def apply_insertions(
    note_path: Path,
    decisions: list[MatchDecision],
    dry_run: bool,
    subject_label: str,
    asset_dir: Path,
) -> tuple[int, int]:
    lines = note_path.read_text(encoding="utf-8").splitlines()
    existing_text = "\n".join(lines)
    lecture_number = extract_lecture_number(note_path)
    if lecture_number is None:
        print(f"[skip] Could not determine identifier for {note_path}")
        return (0, 0)

    inserts: list[tuple[int, list[str]]] = []
    linked = 0
    planned_filenames: set[str] = set()

    for decision in decisions:
        snippet, image_paths = insertion_snippet(decision, lecture_number, subject_label, asset_dir)
        filenames = [path.name for path in image_paths]
        if any(filename in existing_text or filename in planned_filenames for filename in filenames):
            print(
                f"[skip] {note_path.name} :: {decision.candidate.heading_text} already references "
                f"{', '.join(filenames)}"
            )
            continue
        match_summary = ", ".join(
            f"p{match.slide.page_number} score={match.total:.3f} "
            f"(sem={match.semantic:.3f}, title={match.title:.3f}, math={match.math_bonus:.3f}, visual={match.visual_bonus:.3f})"
            for match in decision.matches
        )
        action = "review" if decision.review_needed else "insert"
        print(f"[{action}] {note_path.name} :: {decision.candidate.heading_text} -> {match_summary}")
        planned_filenames.update(filenames)
        linked += len(decision.matches)
        if dry_run:
            continue
        inserts.append((decision.candidate.heading_line + 1, snippet))

    if dry_run or not inserts:
        return (0, linked)

    for line_number, snippet in sorted(inserts, key=lambda item: item[0], reverse=True):
        lines[line_number:line_number] = snippet

    note_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return (0, linked)


def materialize_images(
    note_path: Path,
    decisions: list[MatchDecision],
    document: Any,
    dry_run: bool,
    subject_label: str,
    asset_dir: Path,
) -> int:
    lecture_number = extract_lecture_number(note_path)
    if lecture_number is None:
        return 0
    asset_folder = asset_dir / lecture_number
    if not dry_run:
        asset_folder.mkdir(parents=True, exist_ok=True)

    created = 0
    for decision in decisions:
        for match in decision.matches:
            filename = image_filename(subject_label, lecture_number, match.slide.page_number, decision.candidate.concept_slug)
            output_path = asset_folder / filename
            if output_path.exists():
                continue
            created += 1
            if dry_run:
                print(f"[dry-run] would render {output_path}")
                continue
            render_slide_image(document, match.slide.page_number, output_path, dpi=300)
    return created


def filter_decisions(
    decisions: list[MatchDecision],
    min_score: float,
    generic_headings: set[str],
) -> list[MatchDecision]:
    filtered: list[MatchDecision] = []
    for decision in decisions:
        if not decision.matches:
            continue
        top = decision.matches[0]
        threshold = max(min_score + 0.05, 0.52) if is_generic_heading(decision.candidate, generic_headings) else min_score
        low_evidence = top.total < 0.38 and top.semantic < 0.30
        weak_title_and_semantics = top.total < 0.40 and top.title < 0.20 and top.semantic < 0.25
        if top.total < threshold or low_evidence or weak_title_and_semantics:
            print(
                f"[skip] {decision.candidate.note_path.name} :: {decision.candidate.heading_text} "
                f"best score {top.total:.3f} below threshold {threshold:.3f}"
            )
            continue
        filtered.append(decision)
    return filtered


def resolve_notes(note_arg: str | None, notes_dir_arg: str) -> list[Path]:
    if note_arg:
        return [Path(note_arg)]
    notes_dir = Path(notes_dir_arg)
    if not notes_dir.exists():
        return []
    return sorted(
        path
        for path in notes_dir.glob("*.md")
        if path.name != "index.md"
    )


def process_note(
    note_path: Path,
    pdf_dir: Path,
    min_score: float,
    dry_run: bool,
    aliases: dict[str, set[str]],
    skip_headings: set[str],
    generic_headings: set[str],
    subject_label: str,
    asset_dir: Path,
) -> tuple[int, int]:
    pdf_path = find_matching_pdf(note_path, pdf_dir)
    if pdf_path is None:
        print(f"[skip] No matching course slides found for {note_path}")
        return (0, 0)

    candidates = parse_markdown_candidates(note_path, skip_headings)
    if not candidates:
        print(f"[skip] No candidate sections found in {note_path}")
        return (0, 0)

    document, slides = extract_slide_features(pdf_path)
    try:
        decisions = score_slides(candidates, slides, aliases, generic_headings)
        decisions = filter_decisions(decisions, min_score=min_score, generic_headings=generic_headings)
        created = materialize_images(note_path, decisions, document, dry_run, subject_label, asset_dir)
        _, linked = apply_insertions(note_path, decisions, dry_run, subject_label, asset_dir)
        return (created, linked)
    finally:
        document.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Contextually align lecture notes with course slides using semantic similarity."
    )
    parser.add_argument("--note", help="Single markdown note to process.")
    parser.add_argument(
        "--notes-dir",
        default=str(DEFAULT_NOTES_DIR),
        help=f"Directory containing lecture notes. Default: {DEFAULT_NOTES_DIR}",
    )
    parser.add_argument(
        "--pdf-dir",
        default=str(DEFAULT_PDF_DIR),
        help=f"Directory containing course slides (PDF). Default: {DEFAULT_PDF_DIR}",
    )
    parser.add_argument(
        "--asset-dir",
        default=str(DEFAULT_ASSET_DIR),
        help=(
            "Target asset root. Images are written into identifier-based subfolders. "
            f"Default: {DEFAULT_ASSET_DIR}"
        ),
    )
    parser.add_argument(
        "--min-score",
        type=float,
        default=0.33,
        help="Minimum confidence score required before inserting a match.",
    )
    parser.add_argument(
        "--subject-label",
        default="Lecture",
        help="Prefix used for image filenames and logs (default: 'Lecture').",
    )
    parser.add_argument(
        "--aliases-file",
        help="Path to a JSON file mapping LaTeX commands to alias sets.",
    )
    parser.add_argument(
        "--headings-config",
        help="Path to a JSON file with 'skip' and 'generic' heading lists.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Log proposed insertions and confidence scores without editing files.",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    require_runtime_dependencies()

    aliases: dict[str, set[str]] = {}
    if args.aliases_file:
        with open(args.aliases_file, "r", encoding="utf-8") as f:
            raw_aliases = json.load(f)
            aliases = {k: set(v) for k, v in raw_aliases.items()}

    skip_headings = DEFAULT_SKIP_HEADINGS
    generic_headings = DEFAULT_GENERIC_HEADINGS
    if args.headings_config:
        with open(args.headings_config, "r", encoding="utf-8") as f:
            config = json.load(f)
            if "skip" in config:
                skip_headings = set(config["skip"])
            if "generic" in config:
                generic_headings = set(config["generic"])

    notes = resolve_notes(args.note, args.notes_dir)
    if not notes:
        print("[skip] No lecture notes found to process.")
        return 0

    total_created = 0
    total_linked = 0
    pdf_dir = Path(args.pdf_dir)
    asset_dir = Path(args.asset_dir)

    for note_path in notes:
        created, linked = process_note(
            note_path=note_path,
            pdf_dir=pdf_dir,
            min_score=args.min_score,
            dry_run=args.dry_run,
            aliases=aliases,
            skip_headings=skip_headings,
            generic_headings=generic_headings,
            subject_label=args.subject_label,
            asset_dir=asset_dir,
        )
        total_created += created
        total_linked += linked

    mode = "dry-run" if args.dry_run else "write"
    image_label = "images_planned" if args.dry_run else "images_created"
    link_label = "links_planned" if args.dry_run else "links_inserted"
    print(f"[done] mode={mode} notes={len(notes)} {image_label}={total_created} {link_label}={total_linked}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
