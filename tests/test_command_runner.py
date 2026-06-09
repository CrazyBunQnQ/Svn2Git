from svn2git.commands import CommandResult, CommandRunner, DryRunRunner


def test_dry_run_runner_records_command_without_executing():
    runner = DryRunRunner()

    result = runner.run(["git", "status"], cwd="C:\\work\\git\\Suite")

    assert result.exit_code == 0
    assert runner.commands[0].args == ("git", "status")
    assert runner.commands[0].cwd == "C:\\work\\git\\Suite"
    assert "DRY-RUN" in result.stdout


def test_command_runner_replaces_invalid_subprocess_output(monkeypatch):
    seen_kwargs = {}

    class Completed:
        returncode = 0
        stdout = "ok"
        stderr = ""

    def fake_run(args, **kwargs):
        seen_kwargs.update(kwargs)
        return Completed()

    monkeypatch.setattr("svn2git.commands.subprocess.run", fake_run)

    result = CommandRunner().run(["svn", "update"])

    assert result == CommandResult(0, "ok", "")
    assert seen_kwargs["errors"] == "replace"
