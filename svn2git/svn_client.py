from __future__ import annotations

from svn2git.commands import CommandRunner, DryRunRunner


class SvnClient:
    def __init__(self, runner: CommandRunner | DryRunRunner) -> None:
        self.runner = runner

    def log_xml(self, svn_url: str, username: str | None = None, password: str | None = None) -> str:
        args = ["svn", "log", svn_url, "--xml", "--verbose"]
        if username:
            args.extend(["--username", username])
        if password:
            args.extend(["--password", password])
        result = self.runner.require(args)
        return result.stdout
