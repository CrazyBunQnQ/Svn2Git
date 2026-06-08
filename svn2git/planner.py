from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from svn2git.config import AppConfig, SyncTarget
from svn2git.svn_log import ChangedPath, LogEntry, group_changes_by_branch


@dataclass(frozen=True)
class PlannedRevision:
    revision: int
    author: str
    message: str
    branches: tuple[str, ...]
    svn_url: str
    svn_project_path: str
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
            if target.git_submodule_path:
                lines.append(f"  submodule: {target.git_submodule_path} ({target.git_remote_url})")
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
    current_revision = _read_current_revision(target.git_path)
    for entry in entries:
        if entry.revision <= current_revision:
            continue
        relevant_paths = [change for change in entry.changed_paths if _is_relevant_change(target, change)]
        if not relevant_paths:
            continue
        filtered_entry = LogEntry(entry.revision, entry.author, entry.date, entry.message, relevant_paths)
        grouped = group_changes_by_branch(filtered_entry, target.dir_regex)
        source = _source_for_branches(target, tuple(sorted(grouped)))
        revisions.append(
            PlannedRevision(
                revision=entry.revision,
                author=entry.author,
                message=entry.message,
                branches=tuple(sorted(grouped)),
                svn_url=source[0],
                svn_project_path=source[1],
                entry=filtered_entry,
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


def _is_relevant_change(target: SyncTarget, change: ChangedPath) -> bool:
    if not target.is_submodule:
        return True
    marker = _target_marker(target)
    return marker in _normalize(change.path)


def _target_marker(target: SyncTarget) -> str:
    name = target.name.split(":", 1)[1] if ":" in target.name else target.name
    return f"/{name.lower()}/"


def _normalize(path: str) -> str:
    normalized = path.replace("\\", "/").lower()
    return normalized if normalized.startswith("/") else f"/{normalized}"


def _source_for_branches(target: SyncTarget, branches: tuple[str, ...]) -> tuple[str, str]:
    for branch in branches:
        override = target.branch_overrides.get(branch)
        if override:
            return override.svn_url or target.svn_url, override.svn_project_path
    return target.svn_url, target.svn_project_path
