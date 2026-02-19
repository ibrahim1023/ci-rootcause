from pathlib import Path

from src.parsers.git_diff_parser import parse_git_diff


def test_parse_git_diff_extracts_file_and_hunk_metadata() -> None:
    raw = """diff --git a/src/app.py b/src/app.py
--- a/src/app.py
+++ b/src/app.py
@@ -1,2 +1,3 @@
 import os
+import sys
-print('x')
+print('y')
"""

    parsed = parse_git_diff(raw)

    assert len(parsed.files) == 1
    file_diff = parsed.files[0]
    assert file_diff.change_type == "modified"
    assert file_diff.old_path == "src/app.py"
    assert file_diff.new_path == "src/app.py"
    assert len(file_diff.hunks) == 1
    assert file_diff.hunks[0].old_start == 1
    assert file_diff.hunks[0].new_start == 1
    assert file_diff.hunks[0].added_lines == 2
    assert file_diff.hunks[0].removed_lines == 1


def test_parse_git_diff_normalizes_rename_semantics() -> None:
    raw = """diff --git a/src/a.py b/src/b.py
rename from src/a.py
rename to src/b.py
--- a/src/a.py
+++ b/src/b.py
@@ -1 +1 @@
-print('a')
+print('b')
"""

    parsed = parse_git_diff(raw)

    assert len(parsed.files) == 1
    file_diff = parsed.files[0]
    assert file_diff.change_type == "renamed"
    assert file_diff.renamed_from == "src/a.py"
    assert file_diff.renamed_to == "src/b.py"
    assert file_diff.old_path == "src/a.py"
    assert file_diff.new_path == "src/b.py"


def test_parse_git_diff_with_fixture() -> None:
    raw = Path("fixtures/diffs/rename-and-modify.diff").read_text()

    parsed = parse_git_diff(raw)

    assert len(parsed.files) == 2
    assert parsed.files[0].change_type == "renamed"
    assert parsed.files[1].change_type == "modified"
