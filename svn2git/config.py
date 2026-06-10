from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class BranchOverride:
    svn_project_path: str
    svn_url: str | None = None
    dir_regex: str | None = None
    dir_suffix: str | None = None
    branch_name: str | None = None


@dataclass(frozen=True)
class SyncTarget:
    name: str
    svn_url: str
    svn_project_path: str
    git_path: str
    git_repository_path: str | None = None
    state_path: str | None = None
    target_path: str | None = None
    dir_regex: str | None = None
    dir_suffix: str | None = None
    parent_name: str | None = None
    git_remote_url: str | None = None
    full_sync_interval: int = 1000
    branch_overrides: dict[str, BranchOverride] = field(default_factory=dict)

    @property
    def is_submodule(self) -> bool:
        return self.parent_name is not None


@dataclass(frozen=True)
class ModuleConfig:
    name: str
    svn_project_path: str
    target_path: str
    svn_url: str | None = None
    dir_regex: str | None = None
    dir_suffix: str | None = None
    full_sync_interval: int | None = None
    branch_overrides: dict[str, BranchOverride] = field(default_factory=dict)


@dataclass(frozen=True)
class RepositoryConfig:
    name: str
    svn_url: str
    svn_project_path: str
    git_project_path: str
    git_repository_path: str | None = None
    git_worktree_path: str | None = None
    state_path: str | None = None
    git_remote_url: str | None = None
    dir_regex: str | None = None
    dir_suffix: str | None = None
    full_sync_interval: int = 1000
    modules: dict[str, ModuleConfig] = field(default_factory=dict)
    branch_overrides: dict[str, BranchOverride] = field(default_factory=dict)

    def expand_targets(self) -> list[SyncTarget]:
        if not self.modules:
            return [
                SyncTarget(
                    name=self.name,
                    svn_url=self.svn_url,
                    svn_project_path=self.svn_project_path,
                    git_path=self.git_project_path,
                    git_repository_path=self.git_repository_path,
                    state_path=self.state_path,
                    git_remote_url=self.git_remote_url,
                    dir_regex=self.dir_regex,
                    dir_suffix=self.dir_suffix,
                    full_sync_interval=self.full_sync_interval,
                    branch_overrides=self.branch_overrides,
                )
            ]
        targets = [
        ]
        for module in self.modules.values():
            targets.append(
                SyncTarget(
                    name=f"{self.name}:{module.name}",
                    svn_url=module.svn_url or self.svn_url,
                    svn_project_path=module.svn_project_path,
                    git_path=self.git_project_path,
                    git_repository_path=self.git_repository_path,
                    state_path=self.state_path,
                    target_path=module.target_path,
                    dir_regex=module.dir_regex or self.dir_regex,
                    dir_suffix=module.dir_suffix if module.dir_suffix is not None else self.dir_suffix,
                    full_sync_interval=(
                        module.full_sync_interval if module.full_sync_interval is not None else self.full_sync_interval
                    ),
                    parent_name=self.name,
                    git_remote_url=self.git_remote_url,
                    branch_overrides=module.branch_overrides,
                )
            )
        return targets


@dataclass(frozen=True)
class AppConfig:
    svn_username: str | None
    svn_password: str | None
    git_username: str | None
    git_password: str | None
    user_map: dict[str, str]
    repositories: dict[str, RepositoryConfig]
    mail: dict[str, Any]


def load_config(path: str | Path) -> AppConfig:
    with Path(path).open("r", encoding="utf-8") as stream:
        raw = yaml.safe_load(stream) or {}
    return parse_config(raw)


def parse_config(raw: dict[str, Any]) -> AppConfig:
    mapping = raw.get("svn_git_mapping") or raw.get("svn2git")
    if not isinstance(mapping, dict) or not mapping:
        raise ConfigError("svn_git_mapping is required")

    repositories: dict[str, RepositoryConfig] = {}
    for repo_name, repo_raw in mapping.items():
        repositories[repo_name] = _parse_repository(repo_name, repo_raw or {})

    svn = raw.get("svn") or {}
    git = raw.get("git") or {}
    return AppConfig(
        svn_username=svn.get("username"),
        svn_password=svn.get("password"),
        git_username=git.get("username"),
        git_password=git.get("password"),
        user_map=dict(git.get("user_map") or {}),
        repositories=repositories,
        mail=dict(raw.get("mail") or {}),
    )


def _parse_repository(name: str, raw: dict[str, Any]) -> RepositoryConfig:
    svn_url = _required(raw, f"{name}.svn_url", "svn_url")
    svn_project_path = _required(raw, f"{name}.svn_project_path", "svn_project_path")
    git_repository_path = _optional_str(raw, "git_repository_path")
    git_worktree_path = _optional_str(raw, "git_worktree_path")
    if git_repository_path and not git_worktree_path:
        raise ConfigError(f"{name}.git_worktree_path is required when git_repository_path is configured")
    git_project_path = git_worktree_path or _required(raw, f"{name}.git_project_path", "git_project_path")
    state_path = _optional_str(raw, "state_path")

    if git_repository_path and _same_config_path(git_repository_path, git_project_path):
        raise ConfigError(f"{name}.git_repository_path must differ from {name}.git_worktree_path")

    if raw.get("submodules"):
        raise ConfigError(f"{name}.submodules is no longer supported; use modules with target_path and repo-level git_remote_url")

    modules: dict[str, ModuleConfig] = {}
    for module_name, module_raw in (raw.get("modules") or {}).items():
        prefix = f"{name}.{module_name}"
        modules[module_name] = ModuleConfig(
            name=module_name,
            svn_url=module_raw.get("svn_url"),
            svn_project_path=_required(module_raw, f"{prefix}.svn_project_path", "svn_project_path"),
            target_path=_required(module_raw, f"{prefix}.target_path", "target_path"),
            dir_regex=module_raw.get("dir_regx") or module_raw.get("dir_regex"),
            dir_suffix=module_raw.get("dir_suffix"),
            full_sync_interval=_optional_non_negative_int(
                module_raw,
                f"{prefix}.full_sync_interval",
                "full_sync_interval",
            ),
            branch_overrides=_parse_branch_overrides(prefix, module_raw.get("branch_overrides") or {}),
        )

    return RepositoryConfig(
        name=name,
        svn_url=svn_url,
        svn_project_path=svn_project_path,
        git_project_path=git_project_path,
        git_repository_path=git_repository_path,
        git_worktree_path=git_worktree_path,
        state_path=state_path,
        git_remote_url=raw.get("git_remote_url"),
        dir_regex=raw.get("dir_regx") or raw.get("dir_regex"),
        dir_suffix=raw.get("dir_suffix"),
        full_sync_interval=_non_negative_int(raw, f"{name}.full_sync_interval", "full_sync_interval", default=1000),
        modules=modules,
        branch_overrides=_parse_branch_overrides(name, raw.get("branch_overrides") or {}),
    )


def _parse_branch_overrides(prefix: str, raw: dict[str, Any]) -> dict[str, BranchOverride]:
    overrides: dict[str, BranchOverride] = {}
    for branch, branch_raw in raw.items():
        label = f"{prefix}.branch_overrides.{branch}"
        overrides[str(branch)] = BranchOverride(
            svn_url=branch_raw.get("svn_url"),
            svn_project_path=_required(branch_raw, f"{label}.svn_project_path", "svn_project_path"),
            dir_regex=branch_raw.get("dir_regx") or branch_raw.get("dir_regex"),
            dir_suffix=branch_raw.get("dir_suffix"),
            branch_name=branch_raw.get("branch_name"),
        )
    return overrides


def _required(raw: dict[str, Any], label: str, key: str) -> str:
    value = raw.get(key)
    if value is None or value == "":
        raise ConfigError(f"{label} is required")
    return str(value)


def _optional_str(raw: dict[str, Any], key: str) -> str | None:
    value = raw.get(key)
    if value is None or value == "":
        return None
    return str(value)


def _same_config_path(left: str, right: str) -> bool:
    return left.replace("/", "\\").rstrip("\\").casefold() == right.replace("/", "\\").rstrip("\\").casefold()


def _optional_non_negative_int(raw: dict[str, Any], label: str, key: str) -> int | None:
    if key not in raw or raw.get(key) is None:
        return None
    return _non_negative_int(raw, label, key, default=0)


def _non_negative_int(raw: dict[str, Any], label: str, key: str, default: int) -> int:
    value = raw.get(key, default)
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"{label} must be a non-negative integer") from exc
    if parsed < 0:
        raise ConfigError(f"{label} must be a non-negative integer")
    return parsed
