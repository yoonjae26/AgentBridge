"""Google Antigravity remote agent: human-in-the-loop handoff.

No documented, verified headless task API was available when this adapter was
written, so AgentBridge does **not** start remote executions. ``execute``
generates a task packet and instructions; a developer launches the remote
session with Antigravity's own supported workflow, and the resulting branch is
imported with ``agentbridge remote import``. The adapter never reports that a
remote task ran.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from agentbridge.agents.base import (
    AgentAdapter,
    AvailabilityReport,
    ExecutionRequest,
    ExecutionResult,
    ExecutionState,
)
from agentbridge.agents.capabilities import Capability, OperationSupport, ProviderCapabilities
from agentbridge.config.settings import ProviderSettings
from agentbridge.execution.process import resolve_executable
from agentbridge.workspace.git import Git

DOCS_URL = "https://antigravity.google/docs/remote-agents"
_USERINFO = re.compile(r"(?<=://)[^/@\s]+@")


def sanitize_remote_url(url: str) -> str:
    """Strip any embedded credentials from a git remote URL."""
    return _USERINFO.sub("", url)


def remote_branch_name(task_id: str) -> str:
    return f"agentbridge-remote/{task_id}"


class AntigravityRemoteAdapter(AgentAdapter):
    provider_type = "antigravity_remote"

    def __init__(self, name: str, settings: ProviderSettings) -> None:
        super().__init__(name, settings)
        self.command = settings.command or "agy"

    async def check_availability(self) -> AvailabilityReport:
        executable = resolve_executable(self.command)
        details = [
            "Execution mode: remote_handoff (manual). AgentBridge generates a task packet; "
            "you launch the remote agent yourself.",
            f"Documentation: {DOCS_URL}",
        ]
        if executable:
            details.append(f"Antigravity CLI found at {executable} (commands not auto-invoked)")
        else:
            details.append(
                f"Antigravity CLI '{self.command}' not found; packets can still be generated, "
                "but you need Antigravity installed to launch the remote session."
            )
        # Packet generation is local and always possible. Remote work also needs the
        # repository to be reachable from the remote environment (a git remote).
        return AvailabilityReport(
            available=True, executable=executable, auth="unknown", details=details
        )

    async def get_capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            provider_type=self.provider_type,
            capabilities=frozenset(
                {
                    Capability.EDIT_CODE,
                    Capability.ANALYZE,
                    Capability.REMOTE_WORKSPACE,
                    Capability.HUMAN_IN_THE_LOOP,
                }
            ),
            execution=OperationSupport.MANUAL,
            cancellation=OperationSupport.UNSUPPORTED,
            status_query=OperationSupport.UNSUPPORTED,
            notes=[
                "No verified headless API: execution is a manual handoff.",
                "Remote agents cannot see local worktrees; results return via git.",
                "Token and cost data are not available to AgentBridge.",
            ],
        )

    async def execute(self, request: ExecutionRequest) -> ExecutionResult:
        repo_root = Path(request.repository_info.get("root", "."))
        packet = build_packet(request, repo_root, self.settings.git_remote)
        request.output_dir.mkdir(parents=True, exist_ok=True)
        json_path = request.output_dir / "remote_packet.json"
        md_path = request.output_dir / "remote_packet.md"
        json_path.write_text(json.dumps(packet, indent=2), encoding="utf-8")
        md_path.write_text(render_packet_markdown(packet), encoding="utf-8")
        return ExecutionResult(
            execution_id=request.execution_id,
            provider=self.name,
            state=ExecutionState.HANDOFF_PREPARED,
            summary=(
                "Remote handoff packet prepared. No remote execution was started by "
                f"AgentBridge. Follow {md_path} to launch it."
            ),
            output_path=str(md_path),
            artifacts={"packet_json": str(json_path), "packet_markdown": str(md_path)},
            metadata={"warnings": packet["warnings"]},
        )


def build_packet(request: ExecutionRequest, repo_root: Path, git_remote: str) -> dict[str, Any]:
    git = Git(repo_root)
    warnings: list[str] = []
    remote_url: str | None = None
    result = git.run("remote", "get-url", git_remote, check=False)
    if result.returncode == 0:
        remote_url = sanitize_remote_url(result.stdout.strip())
    else:
        warnings.append(
            f"Git remote '{git_remote}' is not configured. The remote agent needs the "
            "repository on a hosted remote (e.g. GitHub)."
        )
    base_commit = request.repository_info.get("base_commit")
    base_branch = request.repository_info.get("base_branch")
    if remote_url and base_commit:
        contains = git.run("branch", "-r", "--contains", str(base_commit), check=False)
        if contains.returncode != 0 or not contains.stdout.strip():
            warnings.append(
                f"Base commit {str(base_commit)[:12]} is not on any remote-tracking branch; "
                f"push it ('git push {git_remote} {base_branch}') before launching."
            )
    result_branch = remote_branch_name(request.task_id)
    return {
        "packet_version": 1,
        "task_id": request.task_id,
        "title": request.title,
        "description": request.description,
        "role": request.role,
        "acceptance_criteria": request.acceptance_criteria,
        "expected_files": request.expected_files,
        "repository": {
            "remote": git_remote,
            "url": remote_url,
            "base_branch": base_branch,
            "base_commit": base_commit,
        },
        "deliverables": {
            "result_branch": result_branch,
            "instructions": (
                f"Create branch '{result_branch}' from the base commit, implement the task, "
                "commit, and push the branch (or open a pull request from it). Do not push "
                "to the base branch."
            ),
        },
        "prompt": request.prompt,
        "import_command": (
            f"agentbridge remote import {request.task_id} --branch {result_branch} "
            f"--remote {git_remote}"
        ),
        "warnings": warnings,
        "documentation": DOCS_URL,
        "status_note": "This packet does not mean the task ran. It is a handoff.",
    }


def render_packet_markdown(packet: dict[str, Any]) -> str:
    repo = packet["repository"]
    lines = [
        f"# Remote handoff: {packet['task_id']}",
        "",
        "> AgentBridge has **not** executed this task. Launch it yourself using a",
        f"> supported Antigravity workflow ({packet['documentation']}).",
        "",
        f"**Title:** {packet['title']}",
        "",
        "## Repository",
        "",
        f"- Remote: `{repo['remote']}` {repo['url'] or '(not configured)'}",
        f"- Base branch: `{repo['base_branch']}`",
        f"- Base commit: `{repo['base_commit']}`",
        "",
        "## Acceptance criteria",
        "",
        *[f"- {item}" for item in packet["acceptance_criteria"] or ["(none specified)"]],
        "",
        "## Steps",
        "",
        "1. Make sure the base commit is pushed to the remote.",
        "2. Start a remote agent session attached to this repository using Antigravity.",
        "3. Give it the prompt below.",
        f"4. Ask it to push its work to branch `{packet['deliverables']['result_branch']}`.",
        "5. When it finishes, import and validate the result locally:",
        "",
        "```bash",
        packet["import_command"],
        "```",
        "",
        "6. Review the validation report, then approve or reject with",
        f"   `agentbridge tasks approve {packet['task_id']}` / `agentbridge tasks reject ...`.",
        "",
        "## Prompt",
        "",
        "```text",
        packet["prompt"],
        "```",
    ]
    if packet["warnings"]:
        lines += ["", "## Warnings", "", *[f"- {w}" for w in packet["warnings"]]]
    return "\n".join(lines) + "\n"
