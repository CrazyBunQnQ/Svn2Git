from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import PureWindowsPath
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


@dataclass(frozen=True)
class SyncTarget:
    name: str
    svn_url: str
    svn_project_path: str
    git_path: str
    dir_regex: str | None = None
    dir_suffix: str | None = None
    parent_name: str | None = None
    git_submodule_path: str | None = None
    git_remote_url: str | None = None
    branch_overrides: dict[str, BranchOverride] = field(default_factory=dict)

    @property
    def is_submodule(self) -> bool:
        return self.parent_name is not None


@dataclass(frozen=True)
class SubmoduleConfig:
    name: str
    svn_project_path: str
    git_submodule_path: str
    git_remote_url: str
    svn_url: str | None = None
    dir_regex: str | None = None
    dir_suffix: str | None = None
    branch_overrides: dict[str, BranchOverride] = field(default_factory=dict)


@dataclass(frozen=True)
class RepositoryConfig:
    name: str
    svn_url: str
    svn_project_path: str
    git_project_path: str
    dir_regex: str | None = None
    dir_suffix: str | None = None
    submodules: dict[str, SubmoduleConfig] = field(default_factory=dict)
    branch_overrides: dict[str, BranchOverride] = field(default_factory=dict)

    def expand_targets(self) -> list[SyncTarget]:
        targets = [
            SyncTarget(
                name=self.name,
                svn_url=self.svn_url,
                svn_project_path=self.svn_project_path,
                git_path=self.git_project_path,
                dir_regex=self.dir_regex,
                dir_suffix=self.dir_suffix,
                branch_overrides=self.branch_overrides,
            )
        ]
        for submodule in self.submodules.values():
            targets.append(
                SyncTarget(
                    name=f"{self.name}:{submodule.name}",
                    svn_url=submodule.svn_url or self.svn_url,
                    svn_project_path=submodule.svn_project_path,
                    git_path=_join_path(self.git_project_path, submodule.git_submodule_path),
                    dir_regex=submodule.dir_regex or self.dir_regex,
                    dir_suffix=submodule.dir_suffix if submodule.dir_suffix is not None else self.dir_suffix,
                    parent_name=self.name,
                    git_submodule_path=submodule.git_submodule_path,
                    git_remote_url=submodule.git_remote_url,
                    branch_overrides=submodule.branch_overrides,
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
    git_project_path = _required(raw, f"{name}.git_project_path", "git_project_path")

    submodules: dict[str, SubmoduleConfig] = {}
    for submodule_name, submodule_raw in (raw.get("submodules") or {}).items():
        prefix = f"{name}.{submodule_name}"
        submodules[submodule_name] = SubmoduleConfig(
            name=submodule_name,
            svn_url=submodule_raw.get("svn_url"),
            svn_project_path=_required(submodule_raw, f"{prefix}.svn_project_path", "svn_project_path"),
            git_submodule_path=_required(submodule_raw, f"{prefix}.git_submodule_path", "git_submodule_path"),
            git_remote_url=_required(submodule_raw, f"{prefix}.git_remote_url", "git_remote_url"),
            dir_regex=submodule_raw.get("dir_regx") or submodule_raw.get("dir_regex"),
            dir_suffix=submodule_raw.get("dir_suffix"),
            branch_overrides=_parse_branch_overrides(prefix, submodule_raw.get("branch_overrides") or {}),
        )

    return RepositoryConfig(
        name=name,
        svn_url=svn_url,
        svn_project_path=svn_project_path,
        git_project_path=git_project_path,
        dir_regex=raw.get("dir_regx") or raw.get("dir_regex"),
        dir_suffix=raw.get("dir_suffix"),
        submodules=submodules,
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
        )
    return overrides


def _required(raw: dict[str, Any], label: str, key: str) -> str:
    value = raw.get(key)
    if value is None or value == "":
        raise ConfigError(f"{label} is required")
    return str(value)


def _join_path(root: str, child: str) -> str:
    return str(PureWindowsPath(root) / child.replace("/", "\\")) if "\\" in root else str(Path(root) / child)
