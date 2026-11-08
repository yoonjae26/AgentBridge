"""Benchmark metric calculations.

Rules: unavailable values stay ``None``; ``not_executable`` records are excluded
from rates (and counted separately); nothing is imputed.
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from collections.abc import Iterable, Sequence
from typing import Any

from agentbridge_bench.models import ExperimentRecord


def _rate(flags: Sequence[bool | None]) -> float | None:
    known = [f for f in flags if f is not None]
    if not known:
        return None
    return round(sum(1 for f in known if f) / len(known), 4)


def _mean(values: Iterable[float | int | None]) -> float | None:
    known = [float(v) for v in values if v is not None]
    return round(statistics.fmean(known), 3) if known else None


def _median(values: Iterable[float | int | None]) -> float | None:
    known = [float(v) for v in values if v is not None]
    return round(statistics.median(known), 3) if known else None


def _sum_known(values: Iterable[float | int | None]) -> tuple[float | None, int]:
    known = [float(v) for v in values if v is not None]
    return (round(sum(known), 6) if known else None, len(known))


def summarize(records: Sequence[ExperimentRecord]) -> dict[str, Any]:
    executed = [r for r in records if r.status != "not_executable"]
    total_hidden = [
        (r.hidden_tests_passed or 0) + (r.hidden_tests_failed or 0)
        for r in executed
        if r.hidden_tests_passed is not None
    ]
    passed_hidden = sum(
        r.hidden_tests_passed or 0 for r in executed if r.hidden_tests_passed is not None
    )
    est_cost, est_n = _sum_known(r.estimated_cost for r in executed)
    meas_cost, meas_n = _sum_known(r.measured_cost for r in executed)
    tokens_in, tin_n = _sum_known(
        (r.token_usage or {}).get("input") if r.token_usage else None for r in executed
    )
    tokens_out, tout_n = _sum_known(
        (r.token_usage or {}).get("output") if r.token_usage else None for r in executed
    )
    interventions, _ = _sum_known(r.human_interventions for r in executed)
    return {
        "runs_total": len(records),
        "runs_executed": len(executed),
        "runs_not_executable": len(records) - len(executed),
        "task_success_rate": _rate(
            [r.test_passed if r.status != "error" else False for r in executed]
        ),
        "test_pass_rate": round(passed_hidden / sum(total_hidden), 4)
        if sum(total_hidden)
        else None,
        "mean_execution_time_seconds": _mean(r.execution_time_seconds for r in executed),
        "median_execution_time_seconds": _median(r.execution_time_seconds for r in executed),
        "total_measured_cost_usd": meas_cost,
        "measured_cost_runs": meas_n,
        "total_estimated_cost_usd": est_cost,
        "estimated_cost_runs": est_n,
        "total_input_tokens": int(tokens_in) if tokens_in is not None else None,
        "input_token_runs": tin_n,
        "total_output_tokens": int(tokens_out) if tokens_out is not None else None,
        "output_token_runs": tout_n,
        "regression_rate": _rate([r.regression_detected for r in executed]),
        "retry_rate": _mean(r.retries for r in executed),
        "failure_rate": _rate([r.status in ("failed", "error") for r in executed]),
        "human_interventions": int(interventions) if interventions is not None else None,
        "merge_success_rate": _rate([r.merge_success for r in executed]),
    }


def summarize_by_configuration(records: Sequence[ExperimentRecord]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[ExperimentRecord]] = defaultdict(list)
    for record in records:
        grouped[record.configuration].append(record)
    return {name: summarize(items) for name, items in sorted(grouped.items())}
