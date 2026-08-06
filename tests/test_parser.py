"""Tests for the parser module."""

from src.parser import parse_page


def test_parse_page_lang_attribute():
    html = '<html lang="en-GB"><body><p>Some text here for testing.</p></body></html>'
    parsed = parse_page(html, min_length=10)
    # Should strip region code: en-GB -> en
    assert parsed["page_lang"] == "en"


def test_parse_page_no_lang():
    html = "<html><body><p>hello world this is a test</p></body></html>"
    parsed = parse_page(html, min_length=1)
    assert parsed["page_lang"] is None


def test_extract_text_blocks_skips_script_and_style():
    html = """
    <html><body>
        <script>var x = 1;</script>
        <style>.red { color: red; }</style>
        <p>This is a real paragraph with enough text.</p>
    </body></html>
    """
    parsed = parse_page(html, min_length=10)
    snippets = [b["text"] for b in parsed["text_blocks"]]
    assert "var x = 1;" not in snippets
    assert ".red { color: red; }" not in snippets
    assert any("real paragraph" in s for s in snippets)


def test_extract_text_blocks_skips_short_text():
    html = "<html><body><p>hi</p><p>This is a much longer paragraph.</p></body></html>"
    parsed = parse_page(html, min_length=10)
    snippets = [b["text"] for b in parsed["text_blocks"]]
    assert "hi" not in snippets
    assert any("much longer" in s for s in snippets)


def test_parse_page_includes_element_metadata():
    html = '<html><body><p id="intro" class="lead">Introduction paragraph here.</p></body></html>'
    parsed = parse_page(html, min_length=5)
    blocks = parsed["text_blocks"]
    assert len(blocks) >= 1
    assert blocks[0]["tag"] == "p"
    assert blocks[0]["id"] == "intro"
    assert "lead" in blocks[0]["classes"]
