from __future__ import annotations

from pathlib import Path
import re
import shutil

from svn2git.config import SyncTarget
from svn2git.svn_log import ChangedPath, LogEntry


class FileSynchronizer:
    def apply_entry(self, target: SyncTarget, entry: LogEntry) -> None:
        git_root = Path(target.git_path)
        git_root.mkdir(parents=True, exist_ok=True)
        for change in entry.changed_paths:
            relative_path = self._relative_path(change, target.dir_regex, target.dir_suffix)
            if relative_path is None:
                continue
            source_relative_path = self._source_relative_path(target, relative_path)
            source = Path(target.svn_project_path) / source_relative_path
            destination = self._safe_destination(git_root, self._destination_path(target, source_relative_path))
            if change.action in {"A", "M", "R"}:
                self._copy(source, destination)
            elif change.action == "D":
                self._delete(destination)

    def apply_full_sync(self, target: SyncTarget, entry: LogEntry, git_branch: str) -> None:
        git_root = Path(target.git_path)
        git_root.mkdir(parents=True, exist_ok=True)
        source_root = Path(target.svn_project_path)
        destination_root = self._safe_destination(git_root, self._destination_root(target))
        destination_root.mkdir(parents=True, exist_ok=True)
        self._reconcile_tree(source_root, destination_root)

    def _relative_path(self, change: ChangedPath, branch_regex: str | None, dir_suffix: str | None = None) -> Path | None:
        path = change.path.strip("/")
        if branch_regex:
            match = re.match(branch_regex, change.path)
            if match:
                branch = match.group(1)
                marker = f"/{branch}/"
                if marker in change.path:
                    path = change.path.split(marker, 1)[1]
        if dir_suffix:
            marker = dir_suffix.strip("/\\")
            if path == marker:
                path = ""
            elif path.startswith(f"{marker}/") or path.startswith(f"{marker}\\"):
                path = path[len(marker) + 1 :]
        return Path(path) if path else None

    def _copy(self, source: Path, destination: Path) -> None:
        if not source.exists():
            return
        if source.is_dir():
            if destination.exists():
                shutil.rmtree(destination)
            shutil.copytree(source, destination, ignore=shutil.ignore_patterns(".svn", ".git", ".metadata"))
            return
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)

    def _delete(self, destination: Path) -> None:
        if destination.is_dir():
            shutil.rmtree(destination)
        elif destination.exists():
            destination.unlink()

    def _source_relative_path(self, target: SyncTarget, relative_path: Path) -> Path:
        if not target.target_path or ":" not in target.name:
            return relative_path
        module_name = target.name.split(":", 1)[1]
        parts = relative_path.parts
        if parts and parts[0].lower() == module_name.lower():
            return Path(*parts[1:]) if len(parts) > 1 else Path()
        return relative_path

    def _destination_path(self, target: SyncTarget, relative_path: Path) -> Path:
        if not target.target_path or target.target_path == ".":
            return relative_path
        return Path(target.target_path) / relative_path

    def _safe_destination(self, git_root: Path, relative_path: Path) -> Path:
        root = git_root.resolve()
        destination = (git_root / relative_path).resolve()
        if root != destination and root not in destination.parents:
            raise ValueError("target path escapes git root")
        return destination

    def _destination_root(self, target: SyncTarget) -> Path:
        if not target.target_path or target.target_path == ".":
            return Path()
        return Path(target.target_path)

    def _reconcile_tree(self, source_root: Path, destination_root: Path) -> None:
        source_entries = self._sync_entry_names(source_root)
        destination_entries = self._sync_entry_names(destination_root)
        for name in destination_entries - source_entries:
            self._delete(destination_root / name)
        for name in source_entries:
            source = source_root / name
            destination = destination_root / name
            if source.is_dir():
                destination.mkdir(parents=True, exist_ok=True)
                self._reconcile_tree(source, destination)
            else:
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination)

    def _sync_entry_names(self, root: Path) -> set[str]:
        ignored = {".svn", ".git", ".metadata", ".svn_version", ".svn_versions", ".svn_full_sync_versions"}
        if not root.exists():
            return set()
        return {path.name for path in root.iterdir() if path.name not in ignored}

    def _version_file(self, git_root: Path, target: SyncTarget) -> Path:
        if not target.parent_name and not target.target_path:
            return git_root / ".svn_version"
        version_dir = git_root / ".svn_versions"
        version_dir.mkdir(parents=True, exist_ok=True)
        return version_dir / target.name.replace(":", "_").replace("/", "_").replace("\\", "_")

    def _full_sync_version_file(self, git_root: Path, target: SyncTarget, git_branch: str) -> Path:
        version_dir = git_root / ".svn_full_sync_versions" / target.name.replace(":", "_").replace("/", "_").replace("\\", "_")
        version_dir.mkdir(parents=True, exist_ok=True)
        return version_dir / git_branch.replace(":", "_").replace("/", "_").replace("\\", "_")
