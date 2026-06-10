from pathlib import Path

from svn2git.config import SyncTarget
from svn2git.files import FileSynchronizer
from svn2git.svn_log import ChangedPath, LogEntry

import pytest


def test_file_synchronizer_copies_modified_files(tmp_path):
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


def test_file_synchronizer_writes_module_files_under_target_path(tmp_path):
    svn_root = tmp_path / "svn"
    git_root = tmp_path / "git"
    source = svn_root / "src" / "app.py"
    source.parent.mkdir(parents=True)
    source.write_text("print('module')\n", encoding="utf-8")

    entry = LogEntry(
        revision=50,
        author="alice",
        date=None,
        message="Add module file",
        changed_paths=[ChangedPath("/repo/project/branches/dev/billing/src/app.py", "M")],
    )
    target = SyncTarget(
        name="suite:billing",
        svn_url="https://svn.example.com/repos/main",
        svn_project_path=str(svn_root),
        git_path=str(git_root),
        dir_regex=r".*/branches/([^/]+).*",
        target_path="modules/billing",
    )

    FileSynchronizer().apply_entry(target, entry)

    assert (git_root / "modules" / "billing" / "src" / "app.py").read_text(encoding="utf-8") == "print('module')\n"


def test_file_synchronizer_writes_incremental_files_to_explicit_worktree_root(tmp_path):
    svn_root = tmp_path / "svn"
    legacy_git_root = tmp_path / "legacy-git"
    sync_worktree = tmp_path / "service-worktree"
    source = svn_root / "src" / "app.py"
    source.parent.mkdir(parents=True)
    source.write_text("print('worktree')\n", encoding="utf-8")

    entry = LogEntry(
        revision=52,
        author="alice",
        date=None,
        message="Copy to service worktree",
        changed_paths=[ChangedPath("/repo/project/branches/dev/billing/src/app.py", "M")],
    )
    target = SyncTarget(
        name="suite:billing",
        svn_url="https://svn.example.com/repos/main",
        svn_project_path=str(svn_root),
        git_path=str(legacy_git_root),
        dir_regex=r".*/branches/([^/]+).*",
        target_path="modules/billing",
    )

    FileSynchronizer().apply_entry(target, entry, sync_worktree)

    assert (sync_worktree / "modules" / "billing" / "src" / "app.py").read_text(encoding="utf-8") == "print('worktree')\n"
    assert not legacy_git_root.exists()


def test_file_synchronizer_rejects_target_path_escape(tmp_path):
    entry = LogEntry(
        revision=51,
        author="alice",
        date=None,
        message="Escape",
        changed_paths=[ChangedPath("/repo/project/branches/dev/billing/src/app.py", "M")],
    )
    target = SyncTarget(
        name="suite:billing",
        svn_url="https://svn.example.com/repos/main",
        svn_project_path=str(tmp_path / "svn"),
        git_path=str(tmp_path / "git"),
        dir_regex=r".*/branches/([^/]+).*",
        target_path="../outside",
    )

    with pytest.raises(ValueError, match="target path escapes git root"):
        FileSynchronizer().apply_entry(target, entry)


def test_full_sync_reconciles_complete_tree_and_writes_branch_baseline(tmp_path):
    svn_root = tmp_path / "svn"
    git_root = tmp_path / "git"
    source = svn_root / "src" / "app.py"
    source.parent.mkdir(parents=True)
    source.write_text("print('fresh')\n", encoding="utf-8")
    (svn_root / ".svn").mkdir()
    stale = git_root / "modules" / "billing" / "stale.py"
    stale.parent.mkdir(parents=True)
    stale.write_text("stale\n", encoding="utf-8")
    git_control = git_root / ".git" / "config"
    git_control.parent.mkdir(parents=True)
    git_control.write_text("[core]\n", encoding="utf-8")
    entry = LogEntry(
        revision=1000,
        author="alice",
        date=None,
        message="Full sync",
        changed_paths=[ChangedPath("/repo/project/branches/dev/billing/src/app.py", "M")],
    )
    target = SyncTarget(
        name="suite:billing",
        svn_url="https://svn.example.com/repos/main",
        svn_project_path=str(svn_root),
        git_path=str(git_root),
        target_path="modules/billing",
    )

    FileSynchronizer().apply_full_sync(target, entry, "dev")

    assert (git_root / "modules" / "billing" / "src" / "app.py").read_text(encoding="utf-8") == "print('fresh')\n"
    assert not stale.exists()
    assert not (git_root / "modules" / "billing" / ".svn").exists()
    assert git_control.exists()


def test_full_sync_reconciles_into_explicit_worktree_root(tmp_path):
    svn_root = tmp_path / "svn"
    legacy_git_root = tmp_path / "legacy-git"
    sync_worktree = tmp_path / "service-worktree"
    source = svn_root / "src" / "app.py"
    source.parent.mkdir(parents=True)
    source.write_text("print('fresh')\n", encoding="utf-8")
    stale = sync_worktree / "modules" / "billing" / "stale.py"
    stale.parent.mkdir(parents=True)
    stale.write_text("stale\n", encoding="utf-8")
    entry = LogEntry(
        revision=1001,
        author="alice",
        date=None,
        message="Full sync worktree",
        changed_paths=[ChangedPath("/repo/project/branches/dev/billing/src/app.py", "M")],
    )
    target = SyncTarget(
        name="suite:billing",
        svn_url="https://svn.example.com/repos/main",
        svn_project_path=str(svn_root),
        git_path=str(legacy_git_root),
        target_path="modules/billing",
    )

    FileSynchronizer().apply_full_sync(target, entry, "dev", sync_worktree)

    assert (sync_worktree / "modules" / "billing" / "src" / "app.py").read_text(encoding="utf-8") == "print('fresh')\n"
    assert not stale.exists()
    assert not legacy_git_root.exists()
