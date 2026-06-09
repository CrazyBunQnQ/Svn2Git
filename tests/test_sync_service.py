from pathlib import Path

from svn2git.commands import CommandResult, DryRunRunner, RecordedCommand
from svn2git.config import load_config
from svn2git.config import ModuleConfig
from svn2git.service import SyncService
from svn2git.svn_log import ChangedPath, LogEntry, parse_svn_log_xml


FIXTURES = Path(__file__).parent / "fixtures"


def test_sync_batches_modules_without_git_submodules():
    config = load_config(FIXTURES / "application_modules.yml")
    entries = parse_svn_log_xml((FIXTURES / "svn_log.xml").read_text(encoding="utf-8"))
    runner = DryRunRunner()

    service = SyncService(runner)
    service.sync(config, "suite", entries, dry_run=True)

    command_text = [" ".join(command.args) for command in runner.commands]
    assert all("git submodule" not in command for command in command_text)
    assert all(".gitmodules" not in command for command in command_text)
    assert "svn update -r 41 Q:\\svn2git-fixture\\svn\\BillingDev" in command_text
    assert "git commit -m SVN version 41: Add billing feature" in command_text
    assert command_text.count("git commit -m SVN version 41: Add billing feature") == 1


def test_legacy_sync_does_not_emit_submodule_commands():
    config = load_config(FIXTURES / "application_legacy.yml")
    entries = parse_svn_log_xml((FIXTURES / "svn_log.xml").read_text(encoding="utf-8"))
    runner = DryRunRunner()

    SyncService(runner).sync(config, "legacy", entries, dry_run=True)

    command_text = [" ".join(command.args) for command in runner.commands]
    assert all("submodule" not in command for command in command_text)
    assert "svn update -r 41 Q:\\svn2git-fixture\\svn\\Legacy" in command_text


class FailingRunner(DryRunRunner):
    def require(self, args, cwd=None):
        if args[:2] == ["git", "push"]:
            raise RuntimeError("push failed")
        return super().require(args, cwd=cwd)


class RecordingFileSynchronizer:
    def __init__(self):
        self.applied = []

    def apply_entry(self, target, entry):
        self.applied.append((target.name, [change.path for change in entry.changed_paths]))


class BranchAwareDryRunRunner(DryRunRunner):
    def __init__(self):
        super().__init__()
        self.branches = set()

    def run(self, args, cwd=None):
        if args[:3] == ["git", "rev-parse", "--verify"]:
            self.commands.append(RecordedCommand(tuple(args), cwd))
            return CommandResult(0 if args[3] in self.branches else 1)
        if args[:3] == ["git", "checkout", "-B"]:
            self.branches.add(args[3])
        return super().run(args, cwd=cwd)


class ExistingRemoteRunner(DryRunRunner):
    def run(self, args, cwd=None):
        if args == ["git", "remote", "get-url", "origin"]:
            self.commands.append(RecordedCommand(tuple(args), cwd))
            return CommandResult(0, "ssh://git.example.com/suite.git\n", "")
        return super().run(args, cwd=cwd)


class MissingRemoteRunner(DryRunRunner):
    def run(self, args, cwd=None):
        if args == ["git", "remote", "get-url", "origin"]:
            self.commands.append(RecordedCommand(tuple(args), cwd))
            return CommandResult(2, "", "missing remote")
        return super().run(args, cwd=cwd)


class MismatchedRemoteRunner(DryRunRunner):
    def run(self, args, cwd=None):
        if args == ["git", "remote", "get-url", "origin"]:
            self.commands.append(RecordedCommand(tuple(args), cwd))
            return CommandResult(0, "ssh://git.example.com/other.git\n", "")
        return super().run(args, cwd=cwd)


def test_sync_raises_when_mutating_command_fails():
    config = load_config(FIXTURES / "application_legacy.yml")
    entries = [
        LogEntry(
            revision=999999999,
            author="alice",
            date=None,
            message="Force push failure",
            changed_paths=[ChangedPath("/repo/project/branches/dev/billing/src/app.py", "M")],
        )
    ]

    try:
        SyncService(FailingRunner()).sync(config, "legacy", entries, dry_run=True)
    except RuntimeError as exc:
        assert str(exc) == "push failed"
    else:
        raise AssertionError("sync should fail when git push fails")


def test_sync_can_skip_git_push_for_local_verification():
    config = load_config(FIXTURES / "application_legacy.yml")
    entries = [
        LogEntry(
            revision=999999999,
            author="alice",
            date=None,
            message="Local verification",
            changed_paths=[ChangedPath("/repo/project/branches/dev/billing/src/app.py", "M")],
        )
    ]
    runner = DryRunRunner()

    SyncService(runner).sync(config, "legacy", entries, dry_run=True, push=False)

    command_text = [" ".join(command.args) for command in runner.commands]
    assert "git commit -m SVN version 999999999: Local verification" in command_text
    assert all("git push" not in command for command in command_text)


def test_sync_validates_existing_repo_remote_url():
    config = load_config(FIXTURES / "application_modules.yml")
    entries = parse_svn_log_xml((FIXTURES / "svn_log.xml").read_text(encoding="utf-8"))
    runner = ExistingRemoteRunner()

    SyncService(runner).sync(config, "suite", entries, dry_run=True)

    command_text = [" ".join(command.args) for command in runner.commands]
    assert "git remote get-url origin" in command_text
    assert "git remote add origin ssh://git.example.com/suite.git" not in command_text


def test_sync_adds_missing_repo_remote_url():
    config = load_config(FIXTURES / "application_modules.yml")
    entries = parse_svn_log_xml((FIXTURES / "svn_log.xml").read_text(encoding="utf-8"))
    runner = MissingRemoteRunner()

    SyncService(runner).sync(config, "suite", entries, dry_run=True)

    command_text = [" ".join(command.args) for command in runner.commands]
    assert "git remote add origin ssh://git.example.com/suite.git" in command_text


def test_sync_rejects_mismatched_repo_remote_url():
    config = load_config(FIXTURES / "application_modules.yml")
    entries = parse_svn_log_xml((FIXTURES / "svn_log.xml").read_text(encoding="utf-8"))

    try:
        SyncService(MismatchedRemoteRunner()).sync(config, "suite", entries, dry_run=True)
    except RuntimeError as exc:
        assert "origin remote mismatch" in str(exc)
    else:
        raise AssertionError("sync should fail when origin remote does not match config")


def test_sync_rejects_duplicate_module_target_paths():
    config = load_config(FIXTURES / "application_modules.yml")
    duplicate = ModuleConfig(
        name="duplicate",
        svn_project_path="Q:\\svn2git-fixture\\svn\\Duplicate",
        target_path="modules/billing",
    )
    object.__setattr__(config.repositories["suite"], "modules", {**config.repositories["suite"].modules, "duplicate": duplicate})
    entries = parse_svn_log_xml((FIXTURES / "svn_log.xml").read_text(encoding="utf-8"))

    try:
        SyncService(DryRunRunner()).sync(config, "suite", entries, dry_run=True)
    except ValueError as exc:
        assert "duplicate module target path" in str(exc)
    else:
        raise AssertionError("sync should fail for duplicate module target paths")


def test_sync_allows_multiple_modules_targeting_git_root():
    config = load_config(FIXTURES / "application_singularity.yml")
    entries = parse_svn_log_xml((FIXTURES / "svn_log_singularity.xml").read_text(encoding="utf-8"))
    runner = DryRunRunner()

    SyncService(runner).sync(config, "singularity", entries, dry_run=True, push=False)

    command_text = [" ".join(command.args) for command in runner.commands]
    assert "git commit -m SVN version 213: Patch Common 2.13" in command_text
    assert "git commit -m SVN version 214: Patch framework platform_2.13" in command_text


def test_mixed_module_revision_syncs_one_repo_batch_with_relevant_paths():
    config = load_config(FIXTURES / "application_modules.yml")
    entry = LogEntry(
        revision=100,
        author="alice",
        date=None,
        message="Mixed module commit",
        changed_paths=[
            ChangedPath("/repo/project/branches/dev/billing/src/app.py", "M"),
            ChangedPath("/repo/project/release/2.0/reporting/report.txt", "M"),
        ],
    )
    recorder = RecordingFileSynchronizer()

    SyncService(DryRunRunner(), file_synchronizer=recorder).sync(config, "suite", [entry], dry_run=False)

    assert ("suite:billing", ["/repo/project/branches/dev/billing/src/app.py"]) in recorder.applied
    assert ("suite:reporting", ["/repo/project/release/2.0/reporting/report.txt"]) in recorder.applied


def test_same_svn_revision_syncs_each_branch_with_only_its_paths():
    config = load_config(FIXTURES / "application_legacy.yml")
    entry = LogEntry(
        revision=100,
        author="alice",
        date=None,
        message="Patch two branches",
        changed_paths=[
            ChangedPath("/repo/project/branches/dev/src/app.py", "M"),
            ChangedPath("/repo/project/branches/release/src/app.py", "M"),
        ],
    )
    recorder = RecordingFileSynchronizer()
    runner = BranchAwareDryRunRunner()

    SyncService(runner, file_synchronizer=recorder).sync(config, "legacy", [entry], dry_run=False, push=False)

    command_text = [" ".join(command.args) for command in runner.commands]
    assert "git checkout -B dev" in command_text
    assert "git checkout -B release" in command_text
    assert command_text.count("git commit -m SVN version 100: Patch two branches") == 2
    assert recorder.applied == [
        ("legacy", ["/repo/project/branches/dev/src/app.py"]),
        ("legacy", ["/repo/project/branches/release/src/app.py"]),
    ]


def test_sync_uses_branch_override_regex_for_file_application(tmp_path):
    config = load_config(FIXTURES / "application_singularity.yml")
    object.__setattr__(config.repositories["singularity"], "git_project_path", str(tmp_path))
    entries = parse_svn_log_xml((FIXTURES / "svn_log_singularity.xml").read_text(encoding="utf-8"))
    recorder = RecordingFileSynchronizer()
    runner = BranchAwareDryRunRunner()

    SyncService(runner, file_synchronizer=recorder).sync(
        config,
        "singularity",
        entries,
        dry_run=False,
    )

    command_text = [" ".join(command.args) for command in runner.commands]
    assert "git checkout -B 2.13" in command_text
    assert "git checkout 2.13" in command_text
    assert "svn update -r 213 F:\\SvnTest\\SingularityCommon-2.13" in command_text
    assert "svn update -r 214 F:\\SvnTest\\SingularityFramework-2.13" in command_text
    assert recorder.applied == [
        ("singularity:common", ["/repo/codes/SafeMg/Singularity/Common/2.13/common/src/Fix.java"]),
        ("singularity:framework", ["/repo/codes/SafeMg/SMPlatform/branches/platform_2.13/platform-resource/src/Fix.java"]),
    ]
