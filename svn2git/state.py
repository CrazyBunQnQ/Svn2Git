from __future__ import annotations

from pathlib import Path

from svn2git.config import SyncTarget


class SyncState:
    def __init__(self, root: str | Path | None) -> None:
        self.root = Path(root) if root else None

    @classmethod
    def for_target(cls, target: SyncTarget) -> "SyncState":
        return cls(target.state_path)

    @property
    def enabled(self) -> bool:
        return self.root is not None

    def read_checkpoint(self, target: SyncTarget) -> int:
        if not self.root:
            return self._read_int(legacy_checkpoint_path(target))
        return self._read_int(self.root / "checkpoints" / target_key(target))

    def write_checkpoint(self, target: SyncTarget, revision: int) -> None:
        if not self.root:
            self._write_int(legacy_checkpoint_path(target), revision)
            return
        self._write_int(self.root / "checkpoints" / target_key(target), revision)

    def read_full_sync_revision(self, target: SyncTarget, git_branch: str) -> int:
        if not self.root:
            return self._read_int(legacy_full_sync_path(target, git_branch))
        return self._read_int(self.root / "full-sync" / target_key(target) / branch_key(git_branch))

    def write_full_sync_revision(self, target: SyncTarget, git_branch: str, revision: int) -> None:
        if not self.root:
            self._write_int(legacy_full_sync_path(target, git_branch), revision)
            return
        self._write_int(self.root / "full-sync" / target_key(target) / branch_key(git_branch), revision)

    def _read_int(self, path: Path) -> int:
        if not path.exists():
            return -1
        try:
            return int(path.read_text(encoding="utf-8").strip())
        except ValueError:
            return -1

    def _write_int(self, path: Path, revision: int) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(str(revision), encoding="utf-8")


def target_key(target: SyncTarget) -> str:
    return _safe_key(target.name)


def branch_key(git_branch: str) -> str:
    return _safe_key(git_branch)


def legacy_checkpoint_path(target: SyncTarget) -> Path:
    git_root = Path(target.git_path)
    if not target.parent_name and not target.target_path:
        return git_root / ".svn_version"
    return git_root / ".svn_versions" / target_key(target)


def legacy_full_sync_path(target: SyncTarget, git_branch: str) -> Path:
    return Path(target.git_path) / ".svn_full_sync_versions" / target_key(target) / branch_key(git_branch)


def _safe_key(value: str) -> str:
    return value.replace(":", "_").replace("/", "_").replace("\\", "_")
