from __future__ import annotations

from dataclasses import dataclass
import subprocess


@dataclass(frozen=True)
class RecordedCommand:
    args: tuple[str, ...]
    cwd: str | None = None


@dataclass(frozen=True)
class CommandResult:
    exit_code: int
    stdout: str = ""
    stderr: str = ""


class CommandRunner:
    def run(self, args: list[str], cwd: str | None = None) -> CommandResult:
        completed = subprocess.run(args, cwd=cwd, capture_output=True, text=True, check=False)
        return CommandResult(completed.returncode, completed.stdout, completed.stderr)

    def require(self, args: list[str], cwd: str | None = None) -> CommandResult:
        result = self.run(args, cwd=cwd)
        if result.exit_code != 0:
            raise RuntimeError(result.stderr or f"command failed: {' '.join(args)}")
        return result


class DryRunRunner:
    def __init__(self) -> None:
        self.commands: list[RecordedCommand] = []

    def run(self, args: list[str], cwd: str | None = None) -> CommandResult:
        command = RecordedCommand(tuple(args), cwd)
        self.commands.append(command)
        return CommandResult(0, f"DRY-RUN {' '.join(args)}", "")

    def require(self, args: list[str], cwd: str | None = None) -> CommandResult:
        return self.run(args, cwd=cwd)
