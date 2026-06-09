from pathlib import Path

import svn2git.cli as cli
from svn2git.cli import main
from svn2git.commands import CommandResult


FIXTURES = Path(__file__).parent / "fixtures"


def test_cli_dry_run_prints_module_paths(capsys):
    exit_code = main([
        "sync",
        "--config",
        str(FIXTURES / "application_modules.yml"),
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
    assert "submodule:" not in output


def test_cli_validate_rejects_invalid_config(capsys):
    exit_code = main(["validate-config", "--config", str(FIXTURES / "application_invalid_submodule.yml")])

    assert exit_code == 2
    assert "suite.billing.svn_project_path" in capsys.readouterr().err


def test_load_entries_queries_all_singularity_module_sources(monkeypatch):
    config = cli.load_config(FIXTURES / "application_singularity.yml")
    requested_urls = []

    class RecordingRunner:
        def require(self, args, cwd=None):
            requested_urls.append(args[2])
            return CommandResult(0, '<log version="1"><logentry revision="1"><author>alice</author><msg>x</msg><paths /></logentry></log>')

    entries = cli._load_entries(config, "singularity", RecordingRunner(), None, False)

    assert entries
    assert requested_urls == [
        "https://192.168.0.182:8443/repo/codes/IOTP/Tobacco/trunk/Singularity/Common",
        "https://192.168.0.182:8443/repo/codes/SafeMg/Singularity/Common/2.13/common",
        "https://192.168.0.182:8443/repo/codes/IOTP/Tobacco/branches/Singularity",
        "https://192.168.0.182:8443/repo/codes/SafeMg/SMPlatform/branches/platform_2.13",
    ]


def test_load_entries_passes_configured_svn_credentials():
    config = cli.load_config(FIXTURES / "application_singularity.yml")
    seen_args = []

    class RecordingRunner:
        def require(self, args, cwd=None):
            seen_args.append(args)
            return CommandResult(0, '<log version="1"><logentry revision="1"><author>alice</author><msg>x</msg><paths /></logentry></log>')

    cli._load_entries(config, "singularity", RecordingRunner(), None, False)

    assert all("--username" in args for args in seen_args)
    assert all("svn_user" in args for args in seen_args)
    assert all("--password" in args for args in seen_args)
    assert all("svn_password" in args for args in seen_args)
