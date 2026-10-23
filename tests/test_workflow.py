from dataclasses import replace
from pathlib import Path
from urllib.parse import unquote

import pytest

from slidelink import core


@pytest.fixture
def decision(tmp_path):
    note = tmp_path / "notes" / "course" / "01_intro.md"
    note.parent.mkdir(parents=True)
    note.write_text("## Neural Network Layers\n\nEach layer transforms input into useful features.\n")
    candidate = core.parse_markdown_candidates(note, set())[0]
    slide = core.SlideFeatures(
        1, "Neural Network Layers", "neural network layers",
        "Neural Network Layers", 1, 0, 1.0, 1.0, True,
    )
    score = core.SlideScore(slide, 0.9, 0.9, 1.0, 0.0, 0.12)
    return core.MatchDecision(candidate, (score,), False)


@pytest.mark.parametrize("relative", [False, True])
def test_image_links_point_to_custom_asset_directory(decision, tmp_path, monkeypatch, relative):
    monkeypatch.chdir(tmp_path)
    assets = Path("slide images (final) #1%")
    if not relative:
        assets = tmp_path / assets
    lines, paths = core.insertion_snippet(decision, "01", "Lecture", assets)
    link = next(line for line in lines if line.startswith("![]("))
    target = link.removeprefix("![](").removesuffix(")")
    assert " " not in target and "#" not in target and "(" not in target
    assert (decision.candidate.note_path.parent / unquote(target)).resolve() == paths[0].resolve()


@pytest.mark.parametrize("review", [False, True])
@pytest.mark.parametrize("newline", ["\n", "\r\n"])
def test_insert_revert_round_trip_preserves_user_content(decision, tmp_path, review, newline):
    note = decision.candidate.note_path
    original = (note.read_text() + "\n\n![[my-diagram.png]]\n![](screenshots/my-photo.png)").replace("\n", newline).encode()
    note.write_bytes(original)
    if review:
        second = replace(decision.matches[0], slide=replace(decision.matches[0].slide, page_number=2))
        decision = replace(decision, matches=(*decision.matches, second), review_needed=True)
    core.apply_insertions(note, [decision], False, "Lecture", tmp_path / "custom assets")
    inserted = note.read_bytes()
    assert core.revert_note(note, dry_run=True) == 1
    assert note.read_bytes() == inserted
    assert core.revert_note(note, dry_run=False) == 1
    assert note.read_bytes() == original
    assert core.revert_note(note, dry_run=False) == 0


def test_revert_preserves_unrelated_embeds_and_whitespace(tmp_path):
    note = tmp_path / "note.md"
    original = b"## Notes\r\n\r\n\r\n![[diagram.png]]\r\n![[other-note#Section]]\r\n![](screenshots/photo.png)\r\n"
    note.write_bytes(original)
    assert core.revert_note(note, False) == 0
    assert note.read_bytes() == original


def test_revert_removes_legacy_slides_but_preserves_code_and_frontmatter(tmp_path):
    note = tmp_path / "note.md"
    image = "![](screenshots/01/Lecture01_Pg001_Neural_Network_Layers.png)\n"
    wiki = "![[screenshots/01/Lecture01_Pg002_Neural_Network_Layers.png]]\n"
    protected = f"---\nexample: |\n  {image}---\n\n````markdown\n```\n{image}````\n~~~markdown\n{wiki}~~~\n"
    review = "<!-- Review Needed: close slide match for 'Neural Network Layers' (p1: 0.900, p2: 0.880) -->\n"
    note.write_text(protected + review + image + wiki + "Keep this.\n")
    assert core.revert_note(note, False) == 1
    assert note.read_text() == protected + "Keep this.\n"


def test_revert_preserves_marked_code_examples_and_notes_added_inside_markers(decision, tmp_path):
    note = decision.candidate.note_path
    lines, _ = core.insertion_snippet(decision, "01", "Lecture", tmp_path / "assets")
    block = "\n".join(lines) + "\n"
    edited_block = block.replace("<!-- slidelink:end -->", "Keep my annotation.\n<!-- slidelink:end -->")
    original = f"```markdown\n{block}```\n\n{edited_block}"
    note.write_text(original)
    assert core.revert_note(note, False) == 0
    assert note.read_text() == original


@pytest.mark.parametrize("text", ["", "the and or", "x y z", "!!!"])
def test_score_slides_skips_documents_without_searchable_words(decision, text):
    slide = replace(decision.matches[0].slide, text=text, top_text=text)
    assert core.score_slides([decision.candidate], [slide], {}, set()) == []


def test_score_slides_accepts_empty_inputs(decision):
    assert core.score_slides([decision.candidate], [], {}, set()) == []
    assert core.score_slides([], [decision.matches[0].slide], {}, set()) == []


def test_revert_does_not_require_pdf_dependencies(tmp_path, monkeypatch):
    note = tmp_path / "note.md"
    note.write_text("Keep my notes.\n")
    monkeypatch.setattr(core, "fitz", None)
    monkeypatch.setattr(core, "TfidfVectorizer", None)
    monkeypatch.setattr("sys.argv", ["slidelink-run", "--note", str(note), "--revert"])
    assert core.main() == 0


def test_cli_dry_run_insert_repeat_and_revert_with_real_pdfs(decision, tmp_path, monkeypatch, capsys):
    note = decision.candidate.note_path
    original = note.read_bytes()
    assets = tmp_path / "slide images (final) #1%"
    scanned_note = note.with_name("00_scanned.md")
    scanned_note.write_bytes(original)
    with core.fitz.open() as document:
        page = document.new_page(width=360, height=240)
        page.insert_text((30, 30), "Neural Network Layers")
        page.insert_text((30, 80), "Each layer transforms input into useful features.")
        page.draw_rect(core.fitz.Rect(30, 100, 260, 200), fill=(0.2, 0.4, 0.8))
        document.save(note.with_suffix(".pdf"))
        with core.fitz.open() as scanned:
            scanned.new_page(width=360, height=240).insert_image(
                page.rect, stream=page.get_pixmap().tobytes("png")
            )
            scanned.save(scanned_note.with_suffix(".pdf"))
    args = ["slidelink-run", "--notes-dir", str(note.parent), "--asset-dir", str(assets)]
    monkeypatch.setattr("sys.argv", args + ["--dry-run"])
    assert core.main() == 0
    assert "No searchable slide text" in capsys.readouterr().out
    assert note.read_bytes() == original
    assert scanned_note.read_bytes() == original
    assert not assets.exists()

    monkeypatch.setattr("sys.argv", args + ["--note", str(scanned_note)])
    assert core.main() == 0
    assert not assets.exists()

    monkeypatch.setattr("sys.argv", args)
    assert core.main() == 0
    inserted = note.read_bytes()
    assert inserted != original
    images = list(assets.rglob("*.png"))
    assert len(images) == 1
    assert core.fitz.Pixmap(images[0]).width == 1500
    image_line = next(line for line in note.read_text().splitlines() if line.startswith("![]("))
    assert (note.parent / unquote(image_line[4:-1])).resolve() == images[0].resolve()
    assert scanned_note.read_bytes() == original
    assert core.main() == 0
    assert note.read_bytes() == inserted

    monkeypatch.setattr("sys.argv", args + ["--revert"])
    assert core.main() == 0
    assert note.read_bytes() == original
    assert images[0].exists()
