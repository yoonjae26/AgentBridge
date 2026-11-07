"""Dependency-graph validation and scheduling helpers."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import TYPE_CHECKING

from agentbridge.errors import PlanValidationError

if TYPE_CHECKING:
    from agentbridge.tasks.models import TaskSpec


def find_cycle(graph: Mapping[str, Iterable[str]]) -> list[str] | None:
    """Return one dependency cycle (as a list of ids) or None."""
    white, grey, black = 0, 1, 2
    color = dict.fromkeys(graph, white)
    stack: list[str] = []

    def visit(node: str) -> list[str] | None:
        color[node] = grey
        stack.append(node)
        for dep in graph.get(node, ()):
            if dep not in color:
                continue
            if color[dep] == grey:
                return [*stack[stack.index(dep) :], dep]
            if color[dep] == white:
                found = visit(dep)
                if found:
                    return found
        stack.pop()
        color[node] = black
        return None

    for node in graph:
        if color[node] == white:
            cycle = visit(node)
            if cycle:
                return cycle
    return None


def topological_order(graph: Mapping[str, Sequence[str]]) -> list[str]:
    """Deterministic topological order (ties broken by insertion order)."""
    cycle = find_cycle(graph)
    if cycle:
        raise PlanValidationError(f"Dependency cycle detected: {' -> '.join(cycle)}")
    order: list[str] = []
    done: set[str] = set()
    remaining = list(graph)
    while remaining:
        progressed = False
        for node in list(remaining):
            if all(dep in done for dep in graph[node]):
                order.append(node)
                done.add(node)
                remaining.remove(node)
                progressed = True
        if not progressed:  # pragma: no cover - guarded by find_cycle
            raise PlanValidationError("Unresolvable dependencies")
    return order


def ancestors(graph: Mapping[str, Sequence[str]], node: str) -> set[str]:
    seen: set[str] = set()
    pending = list(graph.get(node, ()))
    while pending:
        current = pending.pop()
        if current in seen:
            continue
        seen.add(current)
        pending.extend(graph.get(current, ()))
    return seen


def _patterns_overlap(a: str, b: str) -> bool:
    a_base, b_base = a.rstrip("*").rstrip("/"), b.rstrip("*").rstrip("/")
    return a_base == b_base or a_base.startswith(b_base + "/") or b_base.startswith(a_base + "/")


def validate_graph(tasks: Sequence[TaskSpec]) -> list[str]:
    """Validate a task list. Raises on hard errors and returns soft warnings."""
    ids = [task.id for task in tasks]
    duplicates = sorted({i for i in ids if ids.count(i) > 1})
    if duplicates:
        raise ValueError(f"duplicate task ids: {', '.join(duplicates)}")
    known = set(ids)
    for task in tasks:
        if task.id in task.dependencies:
            raise ValueError(f"task {task.id} depends on itself")
        missing = [dep for dep in task.dependencies if dep not in known]
        if missing:
            raise ValueError(f"task {task.id} depends on unknown task(s): {', '.join(missing)}")
    graph = {task.id: list(task.dependencies) for task in tasks}
    cycle = find_cycle(graph)
    if cycle:
        raise ValueError(f"dependency cycle detected: {' -> '.join(cycle)}")

    warnings: list[str] = []
    for task in tasks:
        if not task.acceptance_criteria:
            warnings.append(f"{task.id}: no acceptance criteria; success is judged by checks only")
        if task.risk_level.value == "high":
            warnings.append(f"{task.id}: high risk task; human review will be required")
    # Tasks that may run in parallel (neither is an ancestor of the other) and
    # declare overlapping file scopes cannot safely run concurrently.
    for i, first in enumerate(tasks):
        for second in tasks[i + 1 :]:
            related = first.id in ancestors(graph, second.id) or second.id in ancestors(
                graph, first.id
            )
            if related:
                continue
            overlap = [
                (a, b)
                for a in first.expected_files
                for b in second.expected_files
                if _patterns_overlap(a, b)
            ]
            if overlap:
                warnings.append(
                    f"{first.id} and {second.id} may run in parallel but both touch "
                    f"{overlap[0][0]}; overlapping changes will need conflict review"
                )
    return warnings
