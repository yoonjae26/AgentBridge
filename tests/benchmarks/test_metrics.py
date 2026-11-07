from agentbridge.bench.metrics import summarize, summarize_by_configuration
from agentbridge.bench.models import ExperimentRecord


def record(**kw):
    base = {
        "experiment_id": "e",
        "task_id": "t",
        "configuration": "c",
        "repetition": 1,
        "status": "completed",
        "started_at": "s",
        "finished_at": "f",
    }
    return ExperimentRecord(**{**base, **kw})


def test_rates_and_means():
    records = [
        record(
            test_passed=True,
            hidden_tests_passed=4,
            hidden_tests_failed=0,
            execution_time_seconds=10,
            retries=0,
            regression_detected=False,
            merge_success=True,
        ),
        record(
            test_passed=False,
            hidden_tests_passed=1,
            hidden_tests_failed=3,
            execution_time_seconds=20,
            retries=2,
            regression_detected=True,
            merge_success=False,
            status="failed",
        ),
    ]
    s = summarize(records)
    assert s["task_success_rate"] == 0.5
    assert s["test_pass_rate"] == 5 / 8
    assert s["mean_execution_time_seconds"] == 15
    assert s["retry_rate"] == 1
    assert s["regression_rate"] == 0.5
    assert s["failure_rate"] == 0.5
    assert s["merge_success_rate"] == 0.5


def test_missing_data_stays_null():
    s = summarize([record(test_passed=True, hidden_tests_passed=1, hidden_tests_failed=0)])
    assert s["total_estimated_cost_usd"] is None
    assert s["total_measured_cost_usd"] is None
    assert s["total_input_tokens"] is None
    assert s["regression_rate"] is None
    assert s["mean_execution_time_seconds"] is None


def test_costs_only_sum_known_values():
    s = summarize(
        [record(estimated_cost=0.5), record(estimated_cost=None), record(estimated_cost=0.25)]
    )
    assert s["total_estimated_cost_usd"] == 0.75
    assert s["estimated_cost_runs"] == 2


def test_not_executable_excluded_from_rates():
    records = [record(status="not_executable"), record(test_passed=True)]
    s = summarize(records)
    assert s["runs_executed"] == 1
    assert s["runs_not_executable"] == 1
    assert s["task_success_rate"] == 1.0
    only_skipped = summarize([record(status="not_executable")])
    assert only_skipped["task_success_rate"] is None


def test_errors_count_as_unsuccessful():
    s = summarize([record(status="error"), record(test_passed=True)])
    assert s["task_success_rate"] == 0.5


def test_grouping():
    grouped = summarize_by_configuration(
        [record(configuration="a", test_passed=True), record(configuration="b", test_passed=False)]
    )
    assert grouped["a"]["task_success_rate"] == 1.0
    assert grouped["b"]["task_success_rate"] == 0.0
