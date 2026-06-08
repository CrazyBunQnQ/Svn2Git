from __future__ import annotations

from svn2git.commands import CommandRunner, DryRunRunner


class SvnClient:
    def __init__(self, runner: CommandRunner | DryRunRunner) -> None:
        self.runner = runner

    def log_xml(self, svn_url: str) -> str:
        result = self.runner.require(["svn", "log", svn_url, "--xml", "--verbose"])
        return result.stdout
