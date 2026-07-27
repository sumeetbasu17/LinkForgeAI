"""Regression tests for the style-upload article splitter.

Run with:  python backend/tests/test_article_parser.py
      or:  pytest backend/tests/test_article_parser.py
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.article_parser import (  # noqa: E402
    parse_header_line,
    split_into_articles,
)


BODY = "\n".join(
    "This is a reasonably long line of body text inside the post." for _ in range(5)
)


# ─── Header recognition ───────────────────────────────────────────


def test_separators_after_the_number():
    """Any separator, or none at all, still marks a header."""
    for line in (
        "Article 1 — The Best Code Review I Ever Received",  # em dash
        "Article 2 – Title",                                  # en dash
        "Article 3 : Title",
        "Article 4 - Title",
        "Article 5. Title",
        "Article 6 | Title",
        "Article 7 Title",                                    # plain space
        "Article 8",                                          # no title
        "# Article 9 — Title",                                # markdown heading
        "**Article 10 — Title**",                             # bold
        "## Artcle 13 – Title",                               # real-world typo
    ):
        assert parse_header_line(line) is not None, line


def test_in_post_lines_are_not_headers():
    """Numbered lines inside a post must never split it."""
    for line in (
        "Option 1: @Order",
        "Step 2 - deploy",
        "1. Quantize the model",
        "Answer 3 is correct",
        "Point 2 — never do this",
    ):
        assert parse_header_line(line) is None, line


# ─── Splitting ────────────────────────────────────────────────────


def test_em_dash_headers_split_with_single_blank_lines():
    """The exact shape that used to collapse into one post."""
    doc = "\n\n".join(f"Article {i} — Title {i}\n{BODY}" for i in range(1, 11))
    result = split_into_articles(doc)
    assert result["method"] == "article-headers"
    assert len(result["articles"]) == 10
    assert [a["number"] for a in result["articles"]] == list(range(1, 11))


def test_headers_win_over_blank_lines():
    doc = "\n\n\n".join(f"Article {i} : Title\n{BODY}" for i in range(1, 4))
    assert split_into_articles(doc)["method"] == "article-headers"


def test_repeated_word_headings_without_the_article_keyword():
    doc = "\n\n".join(f"Post {i} — Title\n{BODY}" for i in range(1, 6))
    result = split_into_articles(doc)
    assert result["method"] == "numbered-headings"
    assert len(result["articles"]) == 5


def test_tutorial_steps_stay_in_one_post():
    doc = "How I tuned inference:\n\n" + "\n\n".join(
        f"Step {i} - do the thing\nA line of explanation long enough to count."
        for i in range(1, 5)
    )
    result = split_into_articles(doc)
    assert result["method"] == "single"
    assert len(result["articles"]) == 1


def test_numbered_list_stays_in_one_post():
    doc = "How would you design the inference system?\n\n" + "\n\n".join(
        f"{i}. Quantize the model\nRun the 70B model in 4-bit to fit the budget."
        for i in range(1, 5)
    )
    result = split_into_articles(doc)
    assert result["method"] == "single"
    assert len(result["articles"]) == 1


def test_single_post_is_left_alone():
    result = split_into_articles(BODY)
    assert result["method"] == "single"
    assert len(result["articles"]) == 1


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
        if not name.startswith("test_") or not callable(fn):
            continue
        try:
            fn()
            print(f"PASS  {name}")
        except AssertionError as exc:
            failures += 1
            print(f"FAIL  {name}: {exc}")
    print(f"\n{failures} failure(s)")
    sys.exit(1 if failures else 0)
