# Svn2Git Service Architecture

This document describes the service-owned architecture used by the Python Svn2Git implementation.

## Ownership Model

- SVN working copies are service-owned. Only the service should run `svn update` or future reverse-sync operations inside these directories.
- Git sync worktrees are service-owned. The service checks out branches, copies files, commits, and pushes from these worktrees.
- Target Git repositories are developer-facing. Developers clone or fetch from these repositories; they should not edit service sync worktrees directly.
- Service state stores checkpoints, full-sync revision markers, job status, and future lock metadata outside Git worktrees.

## Data Flow

1. CLI, HTTP triggers, scheduled tasks, and hook flows create sync jobs through the job runner.
2. The planner reads service state checkpoints and creates per-target sync plans.
3. The service updates SVN working copies, writes files into the Git sync worktree, commits, and pushes to the target Git repository.
4. Checkpoints are written only after the target Git update succeeds.

## Paths

- `svn_project_path`: service-owned SVN working copy.
- `git_repository_path`: target Git repository path, usually a bare repository or remote URL target.
- `git_worktree_path`: service-owned Git sync worktree used for checkout and commits.
- `state_path`: service state root for checkpoints and job-related data.

## Job Runner

The job runner gives CLI, HTTP service, scheduled triggers, and hooks one execution path. Jobs are keyed by repository and Git branch so overlapping work can be serialized while different repositories remain independent.

## Checkpoints

Checkpoints and full-sync markers live in service state. This prevents accidental commits of state files and keeps Git worktrees disposable.

## Hook Modes

The supported hook modes are:

- Compatibility mode: client hooks call the service reverse-sync API and do not modify local SVN directories.
- Strict server-side mode: `hooks/templates/pre-receive` and `hooks/templates/post-receive` show how a bare repository can call the same service APIs.

Service-generated commits use markers such as `Svn2Git-Origin: svn` or `SVN version ...` so reverse-sync logic can avoid loopback.
