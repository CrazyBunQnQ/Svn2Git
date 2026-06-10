from pathlib import Path

from svn2git.config import SyncTarget
from svn2git.state import SyncState


def test_state_stores_target_checkpoint_outside_git_worktree(tmp_path):
    git_root = tmp_path / "git"
    state_root = tmp_path / "state"
    target = SyncTarget(
        name="suite:billing",
        svn_url="https://svn.example.com/repos/main",
        svn_project_path=str(tmp_path / "svn"),
        git_path=str(git_root),
        state_path=str(state_root),
        target_path="modules/billing",
    )

    SyncState.for_target(target).write_checkpoint(target, 41)

    assert SyncState.for_target(target).read_checkpoint(target) == 41
    assert not (git_root / ".svn_versions").exists()
    assert (state_root / "checkpoints" / "suite_billing").read_text(encoding="utf-8") == "41"


def test_state_stores_full_sync_checkpoint_per_branch(tmp_path):
    state_root = tmp_path / "state"
    target = SyncTarget(
        name="legacy",
        svn_url="https://svn.example.com/repos/main",
        svn_project_path=str(tmp_path / "svn"),
        git_path=str(tmp_path / "git"),
        state_path=str(state_root),
    )

    SyncState.for_target(target).write_full_sync_revision(target, "release/2.0", 1000)

    assert SyncState.for_target(target).read_full_sync_revision(target, "release/2.0") == 1000
    assert (state_root / "full-sync" / "legacy" / "release_2.0").read_text(encoding="utf-8") == "1000"


def test_state_returns_safe_defaults_for_missing_or_malformed_values(tmp_path):
    state_root = tmp_path / "state"
    target = SyncTarget(
        name="legacy",
        svn_url="https://svn.example.com/repos/main",
        svn_project_path=str(tmp_path / "svn"),
        git_path=str(tmp_path / "git"),
        state_path=str(state_root),
    )
    (state_root / "checkpoints").mkdir(parents=True)
    (state_root / "checkpoints" / "legacy").write_text("not-a-number", encoding="utf-8")

    assert SyncState.for_target(target).read_checkpoint(target) == -1
    assert SyncState.for_target(target).read_full_sync_revision(target, "dev") == -1
