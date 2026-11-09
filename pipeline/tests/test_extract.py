"""Text extraction keeps the whole policy (regression: Microsoft's Services
Agreement and Pinterest's privacy policy were stored cut short)."""

import pytest

from imbroglio import extract

pytestmark = pytest.mark.skipif(extract.trafilatura is None, reason="trafilatura not installed")


def para(n: int) -> str:
    return (f"<p>Section {n}. We collect personal information such as your name, email address and "
            "device identifiers, and we share it with service providers who process it on our "
            "behalf under contract.</p>") * 4


def page(body: str) -> str:
    return f"<html><body><main><h1>Services Agreement</h1>{body}</main></body></html>"


def trafilatura_text(html: str) -> str:
    return extract.trafilatura.extract(html, include_comments=False, include_tables=True, favor_recall=True)


def test_sections_inside_accordion_labels_are_kept():
    # Microsoft's agreement: each section sits in a checkbox <label>, and
    # trafilatura kept only the one section outside them
    sections = "".join(f'<div><input type="checkbox" id="s{n}"><label for="s{n}"><h2>Part {n}</h2>'
                       f"{para(n)}</label></div>" for n in range(2, 10))
    html = page(para(1) + sections)
    assert "Section 5" not in trafilatura_text(html)
    text = extract.extract_text(html)
    assert all(f"Section {n}." in text for n in range(1, 10))


def test_an_ordinary_page_keeps_trafilaturas_cleaner_text():
    html = page("".join(para(n) for n in range(1, 6))
                + "".join(f'<div><a href="/p{n}">Shop product {n}</a></div>' for n in range(60)))
    assert extract.extract_text(html) == trafilatura_text(html)


def test_a_page_that_repeats_its_text_is_not_counted_as_dropped():
    # ebay: the agreement appears twice in the page, so the fallback is longer
    # without having anything trafilatura missed
    body = "".join(para(n) for n in range(1, 8))
    html = page(body + f"<div>{body}</div>")
    assert extract.extract_text(html) == trafilatura_text(html)
