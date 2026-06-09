from __future__ import annotations

from dataclasses import dataclass
import re
from pathlib import Path

from svn2git.config import AppConfig, SyncTarget
from svn2git.svn_log import ChangedPath, LogEntry


@dataclass(frozen=True)
class PlannedRevision:
    revision: int
    author: str
    message: str
    branches: tuple[str, ...]
    git_branch: str
    svn_url: str
    svn_project_path: str
    dir_regex: str | None
    dir_suffix: str | None
    entry: LogEntry


@dataclass(frozen=True)
class TargetPlan:
    target: SyncTarget
    revisions: tuple[PlannedRevision, ...]


@dataclass(frozen=True)
class SyncPlan:
    repo_name: str
    targets: tuple[SyncTarget, ...]
    target_plans: tuple[TargetPlan, ...]
    dry_run: bool

    def render(self) -> str:
        lines = [f"Sync plan for {self.repo_name} ({'dry-run' if self.dry_run else 'execute'})"]
        for target_plan in self.target_plans:
            target = target_plan.target
            lines.append(f"- {target.name}: {target.svn_project_path} -> {target.git_path}")
            if target.target_path:
                lines.append(f"  module: {target.target_path}")
            for revision in target_plan.revisions:
                lines.append(f"  SVN version {revision.revision}: {revision.message}")
                lines.append(f"  branches: {', '.join(revision.branches)}")
                if revision.svn_project_path != target.svn_project_path or revision.svn_url != target.svn_url:
                    lines.append(f"  svn source: {revision.svn_url} {revision.svn_project_path}")
        return "\n".join(lines)


def build_sync_plan(
    config: AppConfig,
    repo_name: str,
    entries: list[LogEntry],
    dry_run: bool = False,
    target_overrides: dict[str, SyncTarget] | None = None,
) -> SyncPlan:
    try:
        repository = config.repositories[repo_name]
    except KeyError as exc:
        raise ValueError(f"repository not found: {repo_name}") from exc

    targets = tuple((target_overrides or {}).get(target.name, target) for target in repository.expand_targets())
    target_plans = tuple(_plan_target(target, entries) for target in targets)
    return SyncPlan(repo_name=repo_name, targets=targets, target_plans=target_plans, dry_run=dry_run)


def _plan_target(target: SyncTarget, entries: list[LogEntry]) -> TargetPlan:
    revisions: list[PlannedRevision] = []
    current_revision = _read_target_revision(target)
    for entry in entries:
        if entry.revision <= current_revision:
            continue
        relevant_paths = [change for change in entry.changed_paths if _is_relevant_change(target, change)]
        if not relevant_paths:
            continue
        filtered_entry = LogEntry(entry.revision, entry.author, entry.date, entry.message, relevant_paths)
        grouped = _group_changes_by_branch(target, filtered_entry)
        for branch, changes in sorted(grouped.items()):
            source_branches = (branch,)
            source = _source_for_branches(target, source_branches)
            branch_entry = LogEntry(entry.revision, entry.author, entry.date, entry.message, changes)
            revisions.append(
                PlannedRevision(
                    revision=entry.revision,
                    author=entry.author,
                    message=entry.message,
                    branches=_branch_names_for_sources(target, source_branches),
                    git_branch=_git_branch_for_sources(target, source_branches),
                    svn_url=source[0],
                    svn_project_path=source[1],
                    dir_regex=source[2],
                    dir_suffix=source[3],
                    entry=branch_entry,
                )
            )
    return TargetPlan(target=target, revisions=tuple(revisions))


def _read_current_revision(git_path: str) -> int:
    version_file = Path(git_path) / ".svn_version"
    if not version_file.exists():
        return -1
    try:
        return int(version_file.read_text(encoding="utf-8").strip())
    except ValueError:
        return -1


def _read_target_revision(target: SyncTarget) -> int:
    if not target.parent_name and not target.target_path:
        return _read_current_revision(target.git_path)
    version_file = Path(target.git_path) / ".svn_versions" / _revision_key(target)
    if not version_file.exists():
        return -1
    try:
        return int(version_file.read_text(encoding="utf-8").strip())
    except ValueError:
        return -1


def _revision_key(target: SyncTarget) -> str:
    return target.name.replace(":", "_").replace("/", "_").replace("\\", "_")


def _is_relevant_change(target: SyncTarget, change: ChangedPath) -> bool:
    if not target.is_submodule:
        return True
    if _override_branch_for_change(target, change):
        return True
    marker = _target_marker(target)
    return marker in _normalize(change.path)


def _target_marker(target: SyncTarget) -> str:
    name = target.name.split(":", 1)[1] if ":" in target.name else target.name
    return f"/{name.lower()}/"


def _normalize(path: str) -> str:
    normalized = path.replace("\\", "/").lower()
    return normalized if normalized.startswith("/") else f"/{normalized}"


def _group_changes_by_branch(target: SyncTarget, entry: LogEntry) -> dict[str, list[ChangedPath]]:
    grouped: dict[str, list[ChangedPath]] = {}
    for change in entry.changed_paths:
        branch = _branch_for_change(change, target.dir_regex)
        if branch == "master":
            branch = _override_branch_for_change(target, change) or branch
        grouped.setdefault(branch, []).append(change)
    return grouped


def _branch_for_change(change: ChangedPath, branch_regex: str | None) -> str:
    if not branch_regex:
        return "master"
    match = re.compile(branch_regex).match(change.path)
    return match.group(1) if match else "master"


def _override_branch_for_change(target: SyncTarget, change: ChangedPath) -> str | None:
    for branch, override in target.branch_overrides.items():
        if not override.dir_regex:
            continue
        if _branch_for_change(change, override.dir_regex) == branch:
            return branch
    return None


def _source_for_branches(target: SyncTarget, branches: tuple[str, ...]) -> tuple[str, str, str | None, str | None]:
    for branch in branches:
        override = target.branch_overrides.get(branch)
        if override:
            return (
                override.svn_url or target.svn_url,
                override.svn_project_path,
                override.dir_regex or target.dir_regex,
                override.dir_suffix if override.dir_suffix is not None else target.dir_suffix,
            )
    return target.svn_url, target.svn_project_path, target.dir_regex, target.dir_suffix


def _branch_names_for_sources(target: SyncTarget, branches: tuple[str, ...]) -> tuple[str, ...]:
    names = []
    for branch in branches:
        override = target.branch_overrides.get(branch)
        names.append(override.branch_name if override and override.branch_name else branch)
    return tuple(sorted(names))


def _git_branch_for_sources(target: SyncTarget, branches: tuple[str, ...]) -> str:
    names = _branch_names_for_sources(target, branches)
    return names[0] if names else "master"
