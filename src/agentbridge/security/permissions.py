"""Command permission checks.

Every command AgentBridge itself executes (validation, git) passes through
``check_command``. Commands proposed by agents, planners or repository files are
never executed; they are untrusted input.
"""

from __future__ import annotations

import re
from pathlib import PurePath

from agentbridge.errors import PolicyViolationError
from agentbridge.security.policies import Policy

# Characters that only make sense to a shell. We never use a shell, so their
# presence means the command was built from untrusted text.
_SHELL_META = re.compile(r"[;&|`$<>\n\r]|\$\(")

_PROTECTED_GIT = (
    ("push", "--force"),
    ("push", "-f"),
    ("push", "--force-with-lease"),
    ("push", "--mirror"),
    ("push", "--delete"),
    ("reset", "--hard"),
    ("clean",),
    ("branch", "-D"),
    ("checkout", "--force"),
    ("checkout", "-f"),
    ("filter-branch",),
    ("filter-repo",),
    ("reflog", "expire"),
    ("gc", "--prune=now"),
    ("update-ref", "-d"),
)

_DESTRUCTIVE_EXECUTABLES = frozenset(
    {
        "rm",
        "rmdir",
        "del",
        "erase",
        "format",
        "mkfs",
        "dd",
        "shred",
        "rd",
        "sudo",
        "su",
        "chmod",
        "chown",
        "curl",
        "wget",
        "powershell",
        "pwsh",
        "cmd",
        "bash",
        "sh",
        "zsh",
    }
)


def _executable_name(arg0: str) -> str:
    name = PurePath(arg0.replace("\\", "/")).name.lower()
    for suffix in (".exe", ".cmd", ".bat"):
        if name.endswith(suffix):
            name = name[: -len(suffix)]
    return name


def is_protected_git_operation(args: list[str]) -> bool:
    """True for git operations that may destroy history or user work."""
    if not args or _executable_name(args[0]) != "git":
        return False
    # Strip global options such as "-C path" / "-c key=value" before the subcommand.
    cleaned: list[str] = []
    skip = False
    for item in args[1:]:
        if skip:
            skip = False
            continue
        if not cleaned and item in ("-C", "-c", "--git-dir", "--work-tree"):
            skip = True
            continue
        cleaned.append(item)
    if not cleaned:
        return False
    for pattern in _PROTECTED_GIT:
        if cleaned[0] != pattern[0]:
            continue
        if len(pattern) == 1:
            return True
        flags = cleaned[1:]
        if any(f == pattern[1] or f.startswith(pattern[1] + "=") for f in flags):
            return True
        # "git push origin +branch" is also a force push
        if pattern[0] == "push" and any(f.startswith("+") for f in flags):
            return True
    return False


def check_command(args: list[str], policy: Policy) -> None:
    """Raise PolicyViolationError unless ``args`` may be executed under ``policy``."""
    if not args:
        raise PolicyViolationError("Refusing to execute an empty command")
    for arg in args:
        if "\x00" in arg:
            raise PolicyViolationError("Refusing command containing NUL bytes")
    executable = _executable_name(args[0])
    if executable in _DESTRUCTIVE_EXECUTABLES:
        raise PolicyViolationError(
            f"Command '{executable}' is not permitted (destructive or shell executable)"
        )
    if any(_SHELL_META.search(arg) for arg in args):
        raise PolicyViolationError(
            "Refusing command containing shell metacharacters; commands run without a shell"
        )
    if is_protected_git_operation(args):
        raise PolicyViolationError(
            f"Protected git operation blocked: {' '.join(args[:3])}",
            hint="Force-push, hard reset, clean and branch deletion are never automated.",
        )
    if executable not in policy.allowed_executables and args[0] not in policy.allowed_executables:
        raise PolicyViolationError(
            f"Executable '{executable}' is not allowed by the '{policy.profile.value}' policy",
            hint="Add it to security.extra_allowed_commands if it is safe for your project.",
        )
    if executable.startswith("python") and len(args) >= 3 and args[1] == "-m":
        module = args[2]
        if module not in policy.allowed_python_modules:
            raise PolicyViolationError(
                f"'python -m {module}' is not allowed by the '{policy.profile.value}' policy"
            )
    if executable.startswith("python") and len(args) >= 2 and args[1] == "-c":
        raise PolicyViolationError("Inline 'python -c' code is not permitted")
