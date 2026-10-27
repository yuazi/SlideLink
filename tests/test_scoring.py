from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import pytest

from slidelink import core


@pytest.fixture
def candidate():
    text = "Neural Network Layers"
    return core.SectionCandidate(Path("01_notes.md"), 0, 3, text, (), (text,), text, (), "Layers")


def slide(page, text="Neural Network Layers", has_visuals=True):
    return core.SlideFeatures(page, text, core.normalize_text(text), text, 1, 5, 0.1, 0.8, has_visuals)


def test_build_checks_are_bounded_and_shared_between_sections(candidate):
    slides = [slide(page) for page in range(1, 101)]
    with patch.object(core, "is_build_of", wraps=core.is_build_of) as check:
        decisions = core.score_slides([candidate] * 10, slides, {}, set())
    assert len(decisions) == 10
    assert check.call_count <= 4 * len(slides)
    assert all(0 < later.page_number - earlier.page_number <= 4 for (later, earlier), _ in check.call_args_list)


@pytest.mark.parametrize("pages, expected", [
    ([1, 2, 4, 5, 6, 10], [5, 6]),
    ([10, 6, 4, 1, 5, 2], [6, 5]),
])
def test_build_bonus_preserves_page_gaps_and_tie_order(candidate, pages, expected):
    decision = core.score_slides([candidate], [slide(page) for page in pages], {}, set())[0]
    assert decision.review_needed
    assert [match.slide.page_number for match in decision.matches] == expected
    assert [match.total for match in decision.matches] == pytest.approx([1.126, 1.126])


def test_nonvisual_slides_do_not_add_build_bonus(candidate):
    decision = core.score_slides([candidate], [slide(1, has_visuals=False), slide(2)], {}, set())[0]
    assert decision.matches[0].slide.page_number == 2
    assert decision.matches[0].total == pytest.approx(0.976)


def test_weak_matches_do_not_gain_build_bonus(candidate):
    unrelated = replace(candidate, heading_text="Water Cycle", context_text="Rain evaporation clouds")
    single = core.score_slides([unrelated], [slide(1)], {}, set())[0]
    repeated = core.score_slides([unrelated], [slide(1), slide(2)], {}, set())[0]
    assert repeated.matches == single.matches


@pytest.mark.parametrize("title", ["Neural Network Layers", "Layers of a Neural Network", "Neural Network Layers explained"])
def test_complete_title_overlap_skips_fuzzy_matching(candidate, title):
    with patch.object(core, "SequenceMatcher", side_effect=AssertionError("Unneeded fuzzy comparison")):
        assert core.title_similarity(candidate, slide(1, title)) == 1.0


def test_math_aliases_match_whole_words_only():
    aliases = {"\\mu": {"mu", "μ"}, "\\mathcal{L}": {"loss", "l"}}
    expanded = core.expand_math_aliases(("\\mu", "\\mathcal{L}"), aliases)
    assert expanded == {"mu", "loss", "l", "mathcal"}
    term = core.SectionCandidate(Path("01_notes.md"), 0, 3, "Mean", (), ("mean",), "mean", ("\\mu",), "Mean")
    inside_words = core.score_slides([term], [slide(1, "multi layer perceptron")], aliases, set())[0]
    whole_word = core.score_slides([term], [slide(1, "mu is the mean")], aliases, set())[0]
    assert inside_words.matches[0].math_bonus == 0.0
    assert whole_word.matches[0].math_bonus > 0.0


def test_partial_title_overlap_still_uses_fuzzy_matching(candidate):
    with patch.object(core, "SequenceMatcher", wraps=core.SequenceMatcher) as compare:
        score = core.title_similarity(candidate, slide(1, "Neural Network Models"))
    assert compare.call_count == 1
    assert 0 < score < 1
