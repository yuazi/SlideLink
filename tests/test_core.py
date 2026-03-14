from pathlib import Path
from slidelink.core import (
    normalize_text,
    slugify,
    token_overlap_score,
    is_generic_heading,
    extract_lecture_number,
    SectionCandidate
)

def test_normalize_text():
    assert normalize_text("Hello World!") == "hello world"
    assert normalize_text("It's a test...") == "it s a test"
    assert normalize_text("Machine Learning (MLP)") == "machine learning mlp"

def test_slugify():
    assert slugify("Machine Learning Concepts") == "Machine_Learning_Concepts"
    assert slugify("This is a very long heading with many words", max_words=3) == "This_Is_A"
    assert slugify("!!!") == "Concept"

def test_token_overlap_score():
    assert token_overlap_score("machine learning", "machine learning basics") == 1.0
    assert token_overlap_score("basics", "machine learning basics") == 1.0
    assert token_overlap_score("no match", "machine learning") == 0.0
    assert token_overlap_score("partial match", "partial") == 0.5

def test_is_generic_heading():
    generic_set = {"overview", "summary"}
    
    # In the set
    candidate1 = SectionCandidate(
        note_path=Path("test.md"),
        heading_line=1,
        heading_level=2,
        heading_text="Overview",
        parent_headings=(),
        context_lines=(),
        context_text="",
        math_terms=(),
        concept_slug="Overview"
    )
    assert is_generic_heading(candidate1, generic_set) is True
    
    # Not in the set, but meets the short heading rule
    candidate2 = SectionCandidate(
        note_path=Path("test.md"),
        heading_line=1,
        heading_level=2,
        heading_text="Architecture",
        parent_headings=(),
        context_lines=(),
        context_text="",
        math_terms=(),
        concept_slug="Architecture"
    )
    assert is_generic_heading(candidate2, generic_set) is True
    
    # Substantive heading
    candidate3 = SectionCandidate(
        note_path=Path("test.md"),
        heading_line=1,
        heading_level=2,
        heading_text="Deep Neural Networks",
        parent_headings=(),
        context_lines=(),
        context_text="",
        math_terms=(),
        concept_slug="Deep_Neural_Networks"
    )
    assert is_generic_heading(candidate3, generic_set) is False

def test_extract_lecture_number():
    assert extract_lecture_number(Path("01_intro.md")) == "01"
    assert extract_lecture_number(Path("5_concepts.md")) == "05"
    assert extract_lecture_number(Path("no_number.md")) is None
