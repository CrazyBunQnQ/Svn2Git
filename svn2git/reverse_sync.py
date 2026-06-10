from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from svn2git.config import AppConfig, SyncTarget


@dataclass(frozen=True)
class ReverseSyncRequest:
    repo_name: str
    git_branch: str
    commit_sha: str
    commit_message: str
    changed_paths: tuple[str, ...]
    module_hint: str | None = None


@dataclass(frozen=True)
class ReverseSyncPlan:
    target_name: str
    svn_project_path: str
    svn_branch: str
    svn_path: Path
    commit_message: str


def service_generated_commit(message: str) -> bool:
    return message.startswith("SVN version ") or "Svn2Git-Origin: svn" in message


def plan_reverse_sync(config: AppConfig, request: ReverseSyncRequest) -> ReverseSyncPlan:
    if service_generated_commit(request.commit_message):
        raise ValueError("service-generated commit is ignored")
    if not request.changed_paths:
        raise ValueError("changed_paths is required")
    try:
        repository = config.repositories[request.repo_name]
    except KeyError as exc:
        raise ValueError(f"repository not found: {request.repo_name}") from exc
    resolved = []
    for raw_path in request.changed_paths:
        changed_path = Path(raw_path.replace("\\", "/"))
        candidates = [target for target in repository.expand_targets() if _matches_target(target, changed_path, request.module_hint)]
        if not candidates:
            raise ValueError(f"changed path does not match reverse mapping: {changed_path}")
        if len(candidates) > 1:
            raise ValueError("module_hint is required for root target reverse mapping")
        target = candidates[0]
        svn_branch, svn_project_path = _reverse_branch(target, request.git_branch)
        svn_path = _svn_relative_path(target, changed_path)
        resolved.append((target, svn_branch, svn_project_path, svn_path))
    first_target, first_branch, first_project_path, first_svn_path = resolved[0]
    for target, svn_branch, svn_project_path, _svn_path in resolved[1:]:
        if (target.name, svn_branch, svn_project_path) != (first_target.name, first_branch, first_project_path):
            raise ValueError("mixed reverse targets are not supported in one commit")
    return ReverseSyncPlan(
        target_name=first_target.name,
        svn_project_path=first_project_path,
        svn_branch=first_branch,
        svn_path=first_svn_path,
        commit_message=_reverse_commit_message(request),
    )


def _matches_target(target: SyncTarget, changed_path: Path, module_hint: str | None) -> bool:
    if target.target_path and target.target_path != ".":
        return changed_path.as_posix().startswith(Path(target.target_path).as_posix().rstrip("/") + "/")
    if target.parent_name and module_hint:
        return target.name.split(":", 1)[1].casefold() == module_hint.casefold()
    if target.parent_name:
        return True
    return True


def _svn_relative_path(target: SyncTarget, changed_path: Path) -> Path:
    if target.target_path and target.target_path != ".":
        target_root = Path(target.target_path)
        return Path(*changed_path.parts[len(target_root.parts) :])
    return changed_path


def _reverse_branch(target: SyncTarget, git_branch: str) -> tuple[str, str]:
    for branch, override in target.branch_overrides.items():
        if override.branch_name == git_branch or branch == git_branch:
            return branch, override.svn_project_path
    return git_branch, target.svn_project_path


def _reverse_commit_message(request: ReverseSyncRequest) -> str:
    return f"{request.commit_message}\n\nGit commit: {request.commit_sha}\nSvn2Git-Origin: git"
