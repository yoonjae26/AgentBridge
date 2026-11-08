"""AgentBench command line: ``agentbridge-bench ...`` and ``agentbridge benchmark ...``."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.markup import escape
from rich.table import Table

from agentbridge.cli.context import handle_errors
from agentbridge.cli.output import console
from agentbridge.errors import ConfigError, NotFoundError
from agentbridge_bench.dataset import (
    default_benchmarks_dir,
    load_configurations,
    load_suites,
    load_tasks,
)
from agentbridge_bench.reports import generate_reports
from agentbridge_bench.runner import run_benchmark

bench_app = typer.Typer(help="AgentBench: reproducible agent evaluation.", no_args_is_help=True)

DirOption = Annotated[
    Path | None,
    typer.Option("--benchmarks-dir", help="Directory with tasks/ and configurations.yaml"),
]


@bench_app.command("list")
@handle_errors
def bench_list(benchmarks_dir: DirOption = None) -> None:
    """List benchmark tasks, suites and configurations."""
    root = benchmarks_dir or default_benchmarks_dir()
    tasks = load_tasks(root)
    table = Table(title=f"AgentBench tasks ({root})")
    for column in ("Task", "Category", "Difficulty", "Timeout (s)"):
        table.add_column(column)
    for task in tasks.values():
        table.add_row(task.task_id, task.task_category.value, task.difficulty, str(task.timeout))
    console.print(table)
    for name, ids in load_suites(root, tasks).items():
        console.print(f"suite [bold]{name}[/bold]: {len(ids)} task(s)")
    for name, config in load_configurations(root).items():
        console.print(
            f"configuration [bold]{name}[/bold] ({config.kind}): {escape(config.description)}"
        )


@bench_app.command("run")
@handle_errors
def bench_run(
    suite_name: Annotated[str, typer.Argument(help="Suite name, or a single task id.")],
    config: Annotated[
        list[str] | None,
        typer.Option("--config", "-c", help="Configuration(s) to run (repeatable)."),
    ] = None,
    repetitions: Annotated[int, typer.Option("--repetitions", "-n", min=1, max=20)] = 1,
    output: Annotated[Path | None, typer.Option("--output", help="Experiments directory.")] = None,
    benchmarks_dir: DirOption = None,
) -> None:
    """Run a benchmark suite under one or more configurations."""
    root = benchmarks_dir or default_benchmarks_dir()
    tasks = load_tasks(root)
    suites = load_suites(root, tasks)
    if suite_name in suites:
        selected = [tasks[i] for i in suites[suite_name]]
    elif suite_name in tasks:
        selected = [tasks[suite_name]]
    else:
        raise NotFoundError(
            f"Unknown suite or task: {suite_name}", hint=f"Suites: {', '.join(suites)}"
        )
    configurations = load_configurations(root)
    names = config or ["mock-oracle"]
    unknown = [n for n in names if n not in configurations]
    if unknown:
        raise ConfigError(
            f"Unknown configuration(s): {', '.join(unknown)}",
            hint=f"Available: {', '.join(configurations)}",
        )
    exp_dir = run_benchmark(
        root,
        output or (root / "experiments"),
        suite_name,
        selected,
        [configurations[n] for n in names],
        repetitions,
        progress=lambda msg: console.print(escape(msg)),
    )
    console.print(f"[green]Done.[/green] Report: {exp_dir / 'report.md'}")


@bench_app.command("report")
@handle_errors
def bench_report(
    experiment_dir: Annotated[Path, typer.Argument(help="Experiment directory.")],
) -> None:
    """Regenerate CSV/Markdown/SVG reports from saved experiment records."""
    if not (experiment_dir / "records").is_dir():
        raise NotFoundError(f"No records/ directory in {experiment_dir}")
    summary = generate_reports(experiment_dir)
    for name, metrics in summary.items():
        console.print(
            f"{name}: success={metrics['task_success_rate']} executed={metrics['runs_executed']}"
        )
    console.print(f"Report: {experiment_dir / 'report.md'}")


def main() -> None:
    """Entry point of the ``agentbridge-bench`` command."""
    bench_app(prog_name="agentbridge-bench")


if __name__ == "__main__":
    main()
