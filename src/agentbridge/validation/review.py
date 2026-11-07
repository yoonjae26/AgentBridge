"""Deterministic diff review.

This is a heuristic, tool-based reviewer that runs on every task. It does not
replace human review; it flags patterns that warrant a closer look. An optional
agent reviewer can be configured in addition (``routing.reviewer``).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from agentbridge.security.secrets import contains_secret
from agentbridge.workspace.diff import DiffSummary

SENSITIVE_PATH_PATTERNS = (
    re.compile(r"^\.github/workflows/"),
    re.compile(r"(^|/)\.gitlab-ci\.yml$"),
    re.compile(r"(^|/)Dockerfile$"),
    re.compile(r"(^|/)\.env(\..*)?$"),
    re.compile(r"(^|/)(id_rsa|id_ed25519)(\.pub)?$"),
    re.compile(r"(^|/)\.gitmodules$"),
    re.compile(r"(^|/)\.gitattributes$"),
    re.compile(r"(^|/)setup\.py$"),
    re.compile(r"(^|/)agentbridge\.yaml$"),
)

_RULES: tuple[tuple[str, str, re.Pattern[str]], ...] = (
    (
        "high",
        "Test skipped or marked xfail",
        re.compile(r"@pytest\.mark\.(skip|xfail)|\bskipTest\("),
    ),
    ("high", "Use of eval/exec", re.compile(r"\b(eval|exec)\s*\(")),
    ("high", "subprocess with shell=True", re.compile(r"shell\s*=\s*True")),
    ("medium", "Assertion weakened to a constant", re.compile(r"^\s*assert\s+True\b")),
    ("medium", "Type checking suppressed", re.compile(r"#\s*type:\s*ignore")),
    ("low", "Leftover TODO/FIXME", re.compile(r"\b(TODO|FIXME|XXX)\b")),
    ("medium", "Broad exception swallowed", re.compile(r"except\s*(Exception)?\s*:\s*pass")),
)


@dataclass(frozen=True)
class Finding:
    severity: str
    message: str
    path: str | None = None
    line: str | None = None


def _added_lines(patch: str) -> list[tuple[str | None, str]]:
    current: str | None = None
    lines: list[tuple[str | None, str]] = []
    for raw in patch.splitlines():
        if raw.startswith("+++ "):
            target = raw[4:].strip()
            current = target[2:] if target.startswith("b/") else None
        elif raw.startswith("+") and not raw.startswith("+++"):
            lines.append((current, raw[1:]))
    return lines


def review_diff(diff: DiffSummary) -> list[Finding]:
    findings: list[Finding] = []
    for change in diff.files:
        if any(p.search(change.path) for p in SENSITIVE_PATH_PATTERNS):
            findings.append(Finding("high", "Sensitive file modified", change.path))
        is_test = "test" in change.path.lower()
        if is_test and change.status == "D":
            findings.append(Finding("high", "Test file deleted", change.path))
    for path, line in _added_lines(diff.patch):
        if contains_secret(line):
            findings.append(Finding("critical", "Possible credential added", path))
            continue
        for severity, message, pattern in _RULES:
            if pattern.search(line):
                findings.append(Finding(severity, message, path, line.strip()[:160]))
    return findings
