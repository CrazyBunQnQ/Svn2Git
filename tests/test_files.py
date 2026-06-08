from pathlib import Path

from svn2git.config import SyncTarget
from svn2git.files import FileSynchronizer
from svn2git.svn_log import ChangedPath, LogEntry


def test_file_synchronizer_copies_modified_files_and_writes_revision(tmp_path):
    svn_root = tmp_path / "svn"
    git_root = tmp_path / "git"
    source = svn_root / "billing" / "src" / "app.py"
    source.parent.mkdir(parents=True)
    source.write_text("print('ok')\n", encoding="utf-8")

    entry = LogEntry(
        revision=41,
        author="alice",
        date=None,
        message="Add billing feature",
        changed_paths=[ChangedPath("/repo/project/branches/dev/billing/src/app.py", "M")],
    )
    target = SyncTarget(
        name="suite:billing",
        svn_url="https://svn.example.com/repos/main",
        svn_project_path=str(svn_root),
        git_path=str(git_root),
        dir_regex=r".*/branches/([^/]+).*",
    )

    FileSynchronizer().apply_entry(target, entry)

    assert (git_root / "billing" / "src" / "app.py").read_text(encoding="utf-8") == "print('ok')\n"
    assert (git_root / ".svn_version").read_text(encoding="utf-8") == "41"


def test_file_synchronizer_deletes_removed_files(tmp_path):
    svn_root = tmp_path / "svn"
    git_root = tmp_path / "git"
    stale = git_root / "billing" / "old.py"
    stale.parent.mkdir(parents=True)
    stale.write_text("old\n", encoding="utf-8")

    entry = LogEntry(
        revision=42,
        author="alice",
        date=None,
        message="Delete stale file",
        changed_paths=[ChangedPath("/repo/project/branches/dev/billing/old.py", "D")],
    )
    target = SyncTarget(
        name="suite:billing",
        svn_url="https://svn.example.com/repos/main",
        svn_project_path=str(svn_root),
        git_path=str(git_root),
        dir_regex=r".*/branches/([^/]+).*",
    )

    FileSynchronizer().apply_entry(target, entry)

    assert not stale.exists()
    assert (git_root / ".svn_version").read_text(encoding="utf-8") == "42"


def test_file_synchronizer_strips_configured_dir_suffix(tmp_path):
    svn_root = tmp_path / "svn"
    git_root = tmp_path / "git"
    source = svn_root / "common-facade" / "src" / "Fix.java"
    source.parent.mkdir(parents=True)
    source.write_text("class Fix {}\n", encoding="utf-8")

    entry = LogEntry(
        revision=213,
        author="alice",
        date=None,
        message="Patch Common 2.13",
        changed_paths=[ChangedPath("/repo/codes/SafeMg/Singularity/Common/2.13/common/common-facade/src/Fix.java", "M")],
    )
    target = SyncTarget(
        name="singularity",
        svn_url="https://svn.example.com/repos/main",
        svn_project_path=str(svn_root),
        git_path=str(git_root),
        dir_regex=r".*/Common/([^/]+)/common/.*",
        dir_suffix="common",
    )

    FileSynchronizer().apply_entry(target, entry)

    assert (git_root / "common-facade" / "src" / "Fix.java").read_text(encoding="utf-8") == "class Fix {}\n"
    assert not (git_root / "common" / "common-facade").exists()
