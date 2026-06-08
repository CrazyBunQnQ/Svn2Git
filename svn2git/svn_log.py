from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import re
import xml.etree.ElementTree as ET


@dataclass(frozen=True)
class ChangedPath:
    path: str
    action: str
    copy_path: str | None = None
    copy_revision: int | None = None


@dataclass(frozen=True)
class LogEntry:
    revision: int
    author: str
    date: datetime | None
    message: str
    changed_paths: list[ChangedPath]


def parse_svn_log_xml(xml_text: str) -> list[LogEntry]:
    root = ET.fromstring(xml_text)
    entries: list[LogEntry] = []
    for node in root.findall("logentry"):
        changed_paths = []
        for path_node in node.findall("./paths/path"):
            copy_revision = path_node.get("copyfrom-rev")
            changed_paths.append(
                ChangedPath(
                    path=(path_node.text or "").strip(),
                    action=path_node.get("action") or "M",
                    copy_path=path_node.get("copyfrom-path"),
                    copy_revision=int(copy_revision) if copy_revision else None,
                )
            )
        entries.append(
            LogEntry(
                revision=int(node.get("revision") or 0),
                author=(node.findtext("author") or "").strip(),
                date=_parse_date(node.findtext("date")),
                message=(node.findtext("msg") or "").strip(),
                changed_paths=changed_paths,
            )
        )
    return entries


def group_changes_by_branch(entry: LogEntry, branch_regex: str | None) -> dict[str, list[ChangedPath]]:
    grouped: dict[str, list[ChangedPath]] = {}
    pattern = re.compile(branch_regex) if branch_regex else None
    for change in entry.changed_paths:
        branch = "master"
        if pattern:
            match = pattern.match(change.path)
            if match:
                branch = match.group(1)
        grouped.setdefault(branch, []).append(change)
    return grouped


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        return datetime.strptime(value[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
