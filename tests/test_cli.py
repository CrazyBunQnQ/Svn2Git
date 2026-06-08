from pathlib import Path

from svn2git.cli import main


FIXTURES = Path(__file__).parent / "fixtures"


def test_cli_dry_run_prints_submodule_paths(capsys):
    exit_code = main([
        "sync",
        "--config",
        str(FIXTURES / "application_submodules.yml"),
        "--repo",
        "suite",
        "--log-xml",
        str(FIXTURES / "svn_log.xml"),
        "--dry-run",
    ])

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "modules/billing" in output
    assert "modules/reporting" in output


def test_cli_validate_rejects_invalid_config(capsys):
    exit_code = main(["validate-config", "--config", str(FIXTURES / "application_invalid_submodule.yml")])

    assert exit_code == 2
    assert "suite.billing.svn_project_path" in capsys.readouterr().err
