"""
Audit B20 Regression Tests: Legal-page markdown renderer HTML escaping,
list tags, heading levels, list numbers > 5, and link scheme sanitization.
"""

from web.app import _markdown_to_html


def test_ordered_list_tags_and_high_numbers():
    """Verify ordered lists use <ol> and </ol>, and support numbers above 5."""
    md = "1. First\n2. Second\n3. Third\n4. Fourth\n5. Fifth\n6. Sixth\n7. Seventh\n"
    html = _markdown_to_html(md)

    assert "<ol>" in html
    assert "</ol>" in html
    assert "</ul>" not in html
    assert "<li>Sixth</li>" in html
    assert "<li>Seventh</li>" in html


def test_unordered_list_tags():
    """Verify unordered lists use <ul> and </ul>."""
    md = "* Item A\n* Item B\n"
    html = _markdown_to_html(md)

    assert "<ul>" in html
    assert "</ul>" in html
    assert "<ol>" not in html


def test_headings_hierarchy():
    """Verify # renders as <h1>, ## as <h2>, ### as <h3>."""
    md = "# Title Level 1\n## Subtitle Level 2\n### Section Level 3"
    html = _markdown_to_html(md)

    assert "<h1>Title Level 1</h1>" in html
    assert "<h2>Subtitle Level 2</h2>" in html
    assert "<h3>Section Level 3</h3>" in html


def test_html_escaping_prevents_xss():
    """Verify raw HTML tags are escaped."""
    md = "Normal text with <script>alert('xss')</script> and <img src=x onerror=alert(1)>"
    html = _markdown_to_html(md)

    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert "<img" not in html
    assert "&lt;img" in html


def test_javascript_links_are_neutralized():
    """Verify javascript: and unsafe URI schemes are sanitized to #."""
    md = "[Click Me](javascript:alert(1))\n[Safe Link](https://example.com)\n[Email](mailto:support@example.com)"
    html = _markdown_to_html(md)

    assert 'href="javascript:' not in html
    assert 'href="#"' in html
    assert 'href="https://example.com"' in html
    assert 'href="mailto:support@example.com"' in html
