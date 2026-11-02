"""Documents path filter: semicolon-separated roots research several repos at once."""

from deep_dive import build_documents_filter_clause, split_path_filter


def test_split_trims_and_drops_blanks():
    assert split_path_filter("Spock-Universal-AI-Wiki; LLMFIT") == [
        "Spock-Universal-AI-Wiki",
        "LLMFIT",
    ]
    assert split_path_filter(" ; ; ") == []
    assert split_path_filter("") == []


def test_single_relative_path_is_a_substring_match():
    clause = build_documents_filter_clause("llmfit", exclude_generated=False)
    assert clause == "(path LIKE '%llmfit%' OR path LIKE '%llmfit%')"


def test_absolute_path_anchors_to_the_subtree():
    clause = build_documents_filter_clause(
        r"D:\Spock-Universal-AI-Wiki", exclude_generated=False
    )
    assert "path LIKE 'D:\\Spock-Universal-AI-Wiki%'" in clause
    assert "LIKE '%D:" not in clause


def test_two_roots_are_or_ed_together():
    clause = build_documents_filter_clause(
        "Spock-Universal-AI-Wiki; LLMFIT", exclude_generated=False
    )
    assert clause.count("OR (path LIKE") == 1
    assert "%Spock-Universal-AI-Wiki%" in clause
    assert "%LLMFIT%" in clause
    assert clause.startswith("((") and clause.endswith("))")


def test_mixed_absolute_and_relative_roots():
    clause = build_documents_filter_clause(
        r"D:\Spock-Universal-AI-Wiki; llmfit", exclude_generated=False
    )
    assert "path LIKE 'D:\\Spock-Universal-AI-Wiki%'" in clause
    assert "path LIKE '%llmfit%'" in clause


def test_extensions_still_and_with_the_path_group():
    clause = build_documents_filter_clause(
        "spock; llmfit", ".py,.rs", ".md", exclude_generated=False
    )
    path_part, _, rest = clause.partition(" AND ")
    assert path_part.startswith("((")
    assert "(lower(path) LIKE '%.py' OR lower(path) LIKE '%.rs')" in rest
    assert "lower(path) NOT LIKE '%.md'" in rest


def test_quotes_are_escaped():
    clause = build_documents_filter_clause("o'brien; spock", exclude_generated=False)
    assert "o''brien" in clause


def test_blank_path_excludes_generated_site_by_default():
    clause = build_documents_filter_clause("")
    assert "NOT LIKE '%\\site\\%'" in clause
    assert "NOT LIKE '%/site/%'" in clause
    assert "NOT LIKE '%search_index.json%'" in clause
    assert build_documents_filter_clause("   ;  ", exclude_generated=False) == ""
    assert build_documents_filter_clause("", exclude_generated=False) == ""


def test_a_site_root_keeps_that_tree_but_still_drops_the_search_index():
    clause = build_documents_filter_clause(r"D:\Spock-Universal-AI-Wiki\site")
    assert "NOT LIKE '%\\site\\%'" not in clause
    assert "NOT LIKE '%/site/%'" not in clause
    assert "NOT LIKE '%search_index.json%'" in clause
    assert "path LIKE 'D:\\Spock-Universal-AI-Wiki\\site%'" in clause
