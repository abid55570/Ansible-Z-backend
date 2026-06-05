from app.services.projectfmt import normalize, normalize_files


def test_normalize_collapses_blank_lines_and_trailing_ws_but_keeps_indent():
    assert normalize("a\n\n\n\nb\n\n\n") == "a\n\nb\n"  # 3+ blank lines -> 1, trailing blanks dropped
    assert normalize("  x  \ny\t\n") == "  x\ny\n"  # trailing ws stripped, indentation kept
    assert normalize("\n\na\n") == "a\n"  # leading blank lines dropped
    assert normalize("a\r\nb\r\n") == "a\nb\n"  # CRLF normalized to LF
    assert normalize("\n\n\n") == ""  # only-blank content -> empty


def test_normalize_files_maps_every_file():
    assert normalize_files({"a.yml": "x\n\n\n", "b": "  y\n"}) == {"a.yml": "x\n", "b": "  y\n"}
