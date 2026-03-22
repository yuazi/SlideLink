from pathlib import Path
from slidelink.core import (
    normalize_text,
    slugify,
    token_overlap_score,
    is_generic_heading,
    extract_lecture_number,
    is_build_of,
    SectionCandidate,
    SlideFeatures
)

def test_is_build_of():
    p1 = SlideFeatures(
        page_number=10,
        text="Introduction to Joint Representations",
        normalized_text="introduction to joint representations",
        top_text="Joint Representations",
        image_count=0,
        drawing_count=5,
        visual_area_ratio=0.05,
        visual_signal=0.2,
        has_visuals=True
    )
    
    # p2 is a build of p1 (more text, same title, next page)
    p2 = SlideFeatures(
        page_number=11,
        text="Introduction to Joint Representations\nMore details about coordination",
        normalized_text="introduction to joint representations more details about coordination",
        top_text="Joint Representations",
        image_count=0,
        drawing_count=8,
        visual_area_ratio=0.07,
        visual_signal=0.3,
        has_visuals=True
    )
    
    # p3 is NOT a build (different title)
    p3 = SlideFeatures(
        page_number=12,
        text="Conclusion",
        normalized_text="conclusion",
        top_text="Summary",
        image_count=0,
        drawing_count=2,
        visual_area_ratio=0.01,
        visual_signal=0.05,
        has_visuals=True
    )

    assert is_build_of(p2, p1) is True
    assert is_build_of(p1, p2) is False
    assert is_build_of(p3, p2) is False
    assert is_build_of(p2, p3) is False

def test_score_slides_build_preference():
    from slidelink.core import score_slides, SectionCandidate, SlideFeatures
    from pathlib import Path

    candidate = SectionCandidate(
        note_path=Path("note.md"),
        heading_line=10,
        heading_level=2,
        heading_text="Joint and Coordinated Representations",
        parent_headings=(),
        context_lines=("Joint and Coordinated Representations", "Multiple modalities", "Shared space", "Aligned encoders"),
        context_text="Joint and Coordinated Representations Multiple modalities Shared space Aligned encoders",
        math_terms=(),
        concept_slug="Joint_And_Coordinated"
    )

    # Page 10 is incomplete
    p10 = SlideFeatures(
        page_number=10,
        text="Joint Representations\nJoint (fusion)\nImage + Text -> Shared Space",
        normalized_text=normalize_text("Joint Representations Joint (fusion) Image + Text -> Shared Space"),
        top_text="Joint and Coordinated Representations",
        image_count=0,
        drawing_count=10,
        visual_area_ratio=0.1,
        visual_signal=0.5,
        has_visuals=True
    )

    # Page 11 is complete
    p11 = SlideFeatures(
        page_number=11,
        text="Joint and Coordinated Representations\nJoint (fusion)\nImage + Text -> Shared Space\nCoordinated\nSeparate spaces + Aligned",
        normalized_text=normalize_text("Joint and Coordinated Representations Joint (fusion) Image + Text -> Shared Space Coordinated Separate spaces + Aligned"),
        top_text="Joint and Coordinated Representations",
        image_count=0,
        drawing_count=15,
        visual_area_ratio=0.15,
        visual_signal=0.7,
        has_visuals=True
    )

    decisions = score_slides([candidate], [p10, p11], aliases={}, generic_headings=set())
    
    assert len(decisions) == 1
    decision = decisions[0]
    # Page 11 should be preferred even if Page 10 had a higher semantic score 
    # (though here Page 11 likely wins on semantic anyway)
    # The build bonus ensures it's preferred if scores are close.
    assert decision.matches[0].slide.page_number == 11

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
