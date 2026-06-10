from svn2git.commands import CommandResult, CommandRunner, DryRunRunner, RecordedCommand
from svn2git.config import SyncTarget
from svn2git.git_repo import GitRepositoryManager


class MissingWorktreeRunner(DryRunRunner):
    def run(self, args, cwd=None):
        if args == ["git", "rev-parse", "--is-inside-work-tree"]:
            self.commands.append(RecordedCommand(tuple(args), cwd))
            return CommandResult(128, "", "not a work tree")
        if args == ["git", "remote", "get-url", "origin"]:
            self.commands.append(RecordedCommand(tuple(args), cwd))
            return CommandResult(0, "Q:\\svn2git-fixture\\repos\\Service.git\n", "")
        if args[:3] == ["git", "rev-parse", "--verify"]:
            self.commands.append(RecordedCommand(tuple(args), cwd))
            return CommandResult(1, "", "missing branch")
        if args == ["git", "diff", "--cached", "--quiet"]:
            self.commands.append(RecordedCommand(tuple(args), cwd))
            return CommandResult(1, "", "")
        return super().run(args, cwd=cwd)


class ExistingWorktreeRunner(DryRunRunner):
    def run(self, args, cwd=None):
        if args == ["git", "rev-parse", "--is-inside-work-tree"]:
            self.commands.append(RecordedCommand(tuple(args), cwd))
            return CommandResult(0, "true\n", "")
        if args == ["git", "remote", "get-url", "origin"]:
            self.commands.append(RecordedCommand(tuple(args), cwd))
            return CommandResult(0, "Q:\\svn2git-fixture\\repos\\Service.git\n", "")
        if args[:3] == ["git", "rev-parse", "--verify"]:
            self.commands.append(RecordedCommand(tuple(args), cwd))
            return CommandResult(0, args[3], "")
        if args == ["git", "diff", "--cached", "--quiet"]:
            self.commands.append(RecordedCommand(tuple(args), cwd))
            return CommandResult(1, "", "")
        return super().run(args, cwd=cwd)


class CleanIndexRunner(ExistingWorktreeRunner):
    def run(self, args, cwd=None):
        if args == ["git", "diff", "--cached", "--quiet"]:
            self.commands.append(RecordedCommand(tuple(args), cwd))
            return CommandResult(0, "", "")
        return super().run(args, cwd=cwd)


class MismatchedOriginRunner(ExistingWorktreeRunner):
    def run(self, args, cwd=None):
        if args == ["git", "remote", "get-url", "origin"]:
            self.commands.append(RecordedCommand(tuple(args), cwd))
            return CommandResult(0, "Q:\\svn2git-fixture\\repos\\Other.git\n", "")
        return super().run(args, cwd=cwd)


def test_git_repo_manager_initializes_missing_sync_worktree_and_pushes_branch():
    runner = MissingWorktreeRunner()
    target = _target()

    manager = GitRepositoryManager(runner)
    manager.prepare(target, "dev")
    manager.commit_and_push(target, "dev", "SVN version 41")

    command_text = _command_text(runner)
    assert "git clone Q:\\svn2git-fixture\\repos\\Service.git Q:\\svn2git-fixture\\worktrees\\Service" in command_text
    assert "git checkout -B dev" in command_text
    assert "git add ." in command_text
    assert "git commit -m SVN version 41" in command_text
    assert "git push origin dev" in command_text


def test_git_repo_manager_initializes_missing_real_sync_worktree_before_using_cwd(tmp_path):
    class CloneOnlyRunner(CommandRunner):
        def __init__(self):
            self.commands = []

        def run(self, args, cwd=None):
            self.commands.append(RecordedCommand(tuple(args), cwd))
            return CommandResult(0, "true\n", "")

        def require(self, args, cwd=None):
            self.commands.append(RecordedCommand(tuple(args), cwd))
            return CommandResult(0, "", "")

    runner = CloneOnlyRunner()
    worktree = tmp_path / "missing-worktree"
    target = SyncTarget(
        name="service",
        svn_url="https://svn.example.com/repos/main",
        svn_project_path=str(tmp_path / "svn"),
        git_path=str(worktree),
        git_repository_path=str(tmp_path / "Service.git"),
    )

    GitRepositoryManager(runner).prepare(target, "dev")

    assert runner.commands[0].args == ("git", "clone", str(tmp_path / "Service.git"), str(worktree))


def test_git_repo_manager_uses_existing_branch_without_recreating_it():
    runner = ExistingWorktreeRunner()
    target = _target()

    GitRepositoryManager(runner).prepare(target, "dev")

    command_text = _command_text(runner)
    assert "git checkout dev" in command_text
    assert "git checkout -B dev" not in command_text


def test_git_repo_manager_fetches_existing_sync_worktree_before_checkout():
    runner = ExistingWorktreeRunner()
    target = _target()

    GitRepositoryManager(runner).prepare(target, "dev")

    command_text = _command_text(runner)
    assert command_text.index("git fetch origin") < command_text.index("git checkout dev")


def test_git_repo_manager_skips_empty_commit_when_index_is_clean():
    runner = CleanIndexRunner()
    target = _target()

    committed = GitRepositoryManager(runner).commit_and_push(target, "dev", "SVN version 41")

    command_text = _command_text(runner)
    assert committed is False
    assert "git commit -m SVN version 41" not in command_text
    assert "git push origin dev" not in command_text


def test_git_repo_manager_rejects_mismatched_origin():
    runner = MismatchedOriginRunner()
    target = _target()

    try:
        GitRepositoryManager(runner).prepare(target, "dev")
    except RuntimeError as exc:
        assert "origin remote mismatch" in str(exc)
    else:
        raise AssertionError("manager should reject mismatched origin")


def test_git_repo_manager_keeps_legacy_no_remote_behavior():
    runner = ExistingWorktreeRunner()
    target = SyncTarget(
        name="legacy",
        svn_url="https://svn.example.com/repos/main",
        svn_project_path="Q:\\svn2git-fixture\\svn\\Legacy",
        git_path="Q:\\svn2git-fixture\\git\\Legacy",
    )

    GitRepositoryManager(runner).prepare(target, "dev")

    command_text = _command_text(runner)
    assert "git remote get-url origin" not in command_text
    assert "git fetch origin" not in command_text
    assert "git checkout dev" in command_text


def _target() -> SyncTarget:
    return SyncTarget(
        name="service",
        svn_url="https://svn.example.com/repos/main",
        svn_project_path="Q:\\svn2git-fixture\\svn\\Service",
        git_path="Q:\\svn2git-fixture\\worktrees\\Service",
        git_repository_path="Q:\\svn2git-fixture\\repos\\Service.git",
    )


def _command_text(runner: DryRunRunner) -> list[str]:
    return [" ".join(command.args) for command in runner.commands]
