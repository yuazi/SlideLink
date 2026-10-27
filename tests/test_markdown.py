import pytest

from slidelink import core


@pytest.mark.parametrize("opening, inner, closing", [
    ("```markdown", "~~~", "```"),
    ("~~~markdown", "```", "~~~"),
    ("````markdown", "```", "`````"),
    ("   ~~~~markdown", "~~~", " ~~~~~  "),
])
def test_fenced_headings_images_and_text_are_not_note_content(tmp_path, opening, inner, closing):
    note = tmp_path / "01_notes.md"
    content = (
        "## Real section\nThese words belong to the notes.\n"
        f"{opening}\n{inner}\n## Example heading\n![](example.png)\n"
        f"This content is only a code example.\n{closing}\n"
        "### Child section\nMore words from the actual notes.\n"
    )
    note.write_text(content)
    candidates = core.parse_markdown_candidates(note, set())
    assert [candidate.heading_text for candidate in candidates] == ["Real section", "Child section"]
    assert candidates[0].context_lines == ("These words belong to the notes.",)
    assert candidates[1].parent_headings == ("Real section",)
    assert candidates[1].heading_line == content.splitlines().index("### Child section")


@pytest.mark.parametrize("fence", ["```", "~~~", "````", "~~~~"])
def test_section_with_only_fenced_code_is_not_a_candidate(tmp_path, fence):
    note = tmp_path / "01_notes.md"
    note.write_text(f"## Code example\n{fence}\nThese are only example words.\n{fence}\n")
    assert core.parse_markdown_candidates(note, set()) == []


@pytest.mark.parametrize("ending", ["---", "..."])
def test_frontmatter_does_not_supply_headings_or_context(tmp_path, ending):
    note = tmp_path / "01_notes.md"
    note.write_text(
        f"---\n## Metadata comment\ntitle: Some words from metadata\n{ending}\n"
        "## Real section\nThese words belong to the notes.\n"
    )
    candidates = core.parse_markdown_candidates(note, set())
    assert [candidate.heading_text for candidate in candidates] == ["Real section"]
    assert candidates[0].parent_headings == ()
    assert candidates[0].heading_line == 4


def test_unclosed_fence_protects_the_rest_of_the_note(tmp_path):
    note = tmp_path / "01_notes.md"
    note.write_text(
        "## Real section\nThese words belong to the notes.\n"
        "~~~markdown\n## Example heading\nThis is still inside the code block.\n"
        "![](screenshots/01/Lecture01_Pg001_Example.png)\n"
    )
    original = note.read_bytes()
    assert [candidate.heading_text for candidate in core.parse_markdown_candidates(note, set())] == ["Real section"]
    assert core.revert_note(note, False) == 0
    assert note.read_bytes() == original


def test_indented_separator_does_not_end_frontmatter(tmp_path):
    note = tmp_path / "01_notes.md"
    note.write_text(
        "---\nexample: |\n  ---\n## Metadata comment\ntitle: These are metadata words\n---\n"
        "## Real section\nThese words belong to the notes.\n"
    )
    assert [candidate.heading_text for candidate in core.parse_markdown_candidates(note, set())] == ["Real section"]


def test_backticks_in_info_text_do_not_open_a_fence(tmp_path):
    note = tmp_path / "01_notes.md"
    note.write_text("```inline `code`\n## Real section\nThese words belong to the notes.\n")
    candidates = core.parse_markdown_candidates(note, set())
    assert [candidate.heading_text for candidate in candidates] == ["Real section"]
    assert candidates[0].heading_line == 1


def test_insert_and_undo_preserve_code_examples(tmp_path):
    note = tmp_path / "01_notes.md"
    example = (
        "~~~~markdown\n~~~\n## Example heading\nThese words are an example.\n"
        "![](screenshots/01/Lecture01_Pg001_Example.png)\n~~~~\n"
    )
    original = f"{example}\n## Actual heading\nThese words belong to the notes.\n"
    note.write_text(original)
    candidates = core.parse_markdown_candidates(note, set())
    slide = core.SlideFeatures(1, "Actual heading", "actual heading", "Actual heading", 1, 0, 0.1, 0.8, True)
    score = core.SlideScore(slide, 0.9, 0.9, 1.0, 0.0, 0.1)
    decisions = [core.MatchDecision(candidate, (score,), False) for candidate in candidates]
    assert core.apply_insertions(note, decisions, False, "Lecture", tmp_path / "images") == 1
    assert note.read_text().startswith(example)
    assert core.revert_note(note, False) == 1
    assert note.read_text() == original
