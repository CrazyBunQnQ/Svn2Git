from pathlib import Path

from svn2git.commands import CommandResult, DryRunRunner, RecordedCommand
from svn2git.config import load_config
from svn2git.service import SyncService
from svn2git.svn_log import ChangedPath, LogEntry, parse_svn_log_xml


FIXTURES = Path(__file__).parent / "fixtures"


def test_submodule_sync_orchestrates_submodule_before_parent_pointer():
    config = load_config(FIXTURES / "application_submodules.yml")
    entries = parse_svn_log_xml((FIXTURES / "svn_log.xml").read_text(encoding="utf-8"))
    runner = DryRunRunner()

    service = SyncService(runner)
    service.sync(config, "suite", entries, dry_run=True)

    command_text = [" ".join(command.args) for command in runner.commands]
    assert "git submodule add ssh://git.example.com/suite/billing.git modules/billing" in command_text
    assert "svn update -r 41 Q:\\svn2git-fixture\\svn\\BillingDev" in command_text
    assert "git commit -m SVN version 41: Add billing feature" in command_text
    assert command_text[-2:] == ["git add .gitmodules modules/billing modules/reporting", "git commit -m Update submodule pointers for SVN sync"]


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


def test_mixed_module_revision_syncs_only_target_relevant_paths():
    config = load_config(FIXTURES / "application_submodules.yml")
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
        ("singularity", ["/repo/codes/SafeMg/Singularity/Common/2.13/common/src/Fix.java"]),
        ("singularity", ["/repo/codes/SafeMg/SMPlatform/branches/platform_2.13/platform-resource/src/Fix.java"]),
    ]
