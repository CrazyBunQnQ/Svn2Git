from pathlib import Path

from svn2git.svn_log import group_changes_by_branch, parse_svn_log_xml


FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_svn_log_xml_and_group_by_branch():
    entries = parse_svn_log_xml((FIXTURES / "svn_log.xml").read_text(encoding="utf-8"))

    assert [entry.revision for entry in entries] == [41, 42]
    assert entries[0].author == "alice"
    assert entries[0].message == "Add billing feature"
    assert entries[0].changed_paths[3].copy_path == "/repo/project/branches/main/billing/src/base.py"
    assert entries[0].changed_paths[3].copy_revision == 40

    grouped = group_changes_by_branch(entries[0], r".*/branches/([^/]+).*")

    assert sorted(grouped) == ["dev"]
    assert [change.action for change in grouped["dev"]] == ["A", "M", "D", "A"]


def test_group_changes_defaults_to_master_without_regex():
    entry = parse_svn_log_xml((FIXTURES / "svn_log.xml").read_text(encoding="utf-8"))[0]

    assert list(group_changes_by_branch(entry, None)) == ["master"]
