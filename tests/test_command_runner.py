from svn2git.commands import DryRunRunner


def test_dry_run_runner_records_command_without_executing():
    runner = DryRunRunner()

    result = runner.run(["git", "status"], cwd="C:\\work\\git\\Suite")

    assert result.exit_code == 0
    assert runner.commands[0].args == ("git", "status")
    assert runner.commands[0].cwd == "C:\\work\\git\\Suite"
    assert "DRY-RUN" in result.stdout
