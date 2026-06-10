# Migration: Working Tree To Service-Owned Paths

This guide moves legacy configurations from a single working tree path to explicit service-owned paths.

## Why Migrate

Legacy configs used `git_project_path` as both the Git worktree and the repository users cared about. The service architecture separates these responsibilities so developers can safely work with target Git repositories while the service owns mutable working directories.

## Path Split

Replace the old shape:

```yaml
git_project_path: F:\GitRepo\Platform
```

with explicit paths:

```yaml
git_repository_path: F:\GitRepo\Platform.git
git_worktree_path: F:\Svn2GitService\worktrees\Platform
state_path: F:\Svn2GitService\state\Platform
```

- `git_repository_path` is the target Git repository. A local bare repository is recommended for service-managed targets.
- `git_worktree_path` is the service-owned sync worktree. 不要手动修改服务自有目录。
- `state_path` is where checkpoints and full-sync state live.

## Initialize A Local Bare Repository

```shell
git init --bare F:\GitRepo\Platform.git
```

The service can create or refresh its sync worktree from this target repository during sync. Developers should clone from `git_repository_path`, not from `git_worktree_path`.

## SVN Working Copies

Keep `svn_project_path` pointed at a service-owned SVN working copy. For modules and branch overrides, each `svn_project_path` should also be service-owned.

## Full Sync And Checkpoints

`full_sync_interval` behavior is unchanged, but full-sync markers and normal checkpoints move to `state_path`. The Git sync worktree no longer needs `.svn_version`, `.svn_versions`, or `.svn_full_sync_versions` files.

## Hook Mode

Use compatibility hook mode first: install the client hook scripts and configure `SVN2GIT_SERVICE_URL` and `SVN2GIT_REPO_NAME`. For repositories that can run server-side hooks, use the templates in `hooks/templates/` as the starting point.

## Validation

After migrating config, run:

```shell
python -m svn2git validate-config --config config/application.yml
python -m svn2git sync --config config/application.yml --repo platform --log-xml tests/fixtures/svn_log.xml --dry-run
```
