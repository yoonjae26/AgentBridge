import pytest
from pydantic import ValidationError

from agentbridge.core.planner import parse_plan, single_plan, standard_plan
from agentbridge.errors import PlanValidationError
from agentbridge.tasks.dependencies import find_cycle, topological_order
from agentbridge.tasks.models import Plan, TaskRole, TaskSpec


def test_topological_order():
    graph = {"a": [], "b": ["a"], "c": ["a"], "d": ["b", "c"]}
    order = topological_order(graph)
    assert order.index("a") < order.index("b") < order.index("d")
    assert order.index("c") < order.index("d")


def test_cycle_detection():
    assert find_cycle({"a": ["b"], "b": ["c"], "c": ["a"]}) is not None
    assert find_cycle({"a": [], "b": ["a"]}) is None
    with pytest.raises(PlanValidationError):
        topological_order({"a": ["b"], "b": ["a"]})


def spec(task_id, deps=(), files=(), role=TaskRole.DEVELOPER):
    return TaskSpec(
        id=task_id,
        title=task_id,
        dependencies=list(deps),
        expected_files=list(files),
        role=role,
        acceptance_criteria=["done"],
    )


def test_plan_rejects_cycles_unknown_and_duplicates():
    with pytest.raises(ValidationError, match="cycle"):
        Plan(objective="x", tasks=[spec("a", ["b"]), spec("b", ["a"])])
    with pytest.raises(ValidationError, match="unknown"):
        Plan(objective="x", tasks=[spec("a", ["zzz"])])
    with pytest.raises(ValidationError, match="duplicate"):
        Plan(objective="x", tasks=[spec("a"), spec("a")])
    with pytest.raises(ValidationError, match="itself"):
        Plan(objective="x", tasks=[spec("a", ["a"])])


def test_parallel_overlap_warning():
    plan = Plan(
        objective="x", tasks=[spec("a", files=["src/app.py"]), spec("b", files=["src/app.py"])]
    )
    assert any("parallel" in w for w in plan.warnings)
    sequential = Plan(
        objective="x",
        tasks=[spec("a", files=["src/app.py"]), spec("b", ["a"], files=["src/app.py"])],
    )
    assert not any("parallel" in w for w in sequential.warnings)


def test_task_id_and_paths_validated():
    with pytest.raises(ValidationError):
        TaskSpec(id="../etc", title="bad")
    with pytest.raises(ValidationError):
        TaskSpec(id="task-1", title="bad", expected_files=["../../secret"])


def test_template_plans():
    assert [t.role for t in single_plan("Do it").tasks] == [TaskRole.DEVELOPER]
    plan = standard_plan("Do it")
    assert [t.role for t in plan.tasks] == [TaskRole.ANALYST, TaskRole.DEVELOPER, TaskRole.REVIEWER]
    assert plan.tasks[2].dependencies == ["task-002"]


def test_parse_plan_from_text_and_strips_unknown_fields():
    text = """Here is the plan:
    {"tasks": [{"id": "task-001", "title": "Build", "role": "developer",
                "command": "rm -rf /", "acceptance_criteria": ["ok"]}]}
    """
    plan = parse_plan(text, "Objective")
    assert plan.objective == "Objective"
    assert plan.tasks[0].title == "Build"
    assert "command" not in plan.tasks[0].model_dump()


@pytest.mark.parametrize(
    "payload",
    [
        "no json here",
        "{not valid json}",
        '{"tasks": []}',
        '{"tasks": [{"id": "a", "title": "x", "dependencies": ["a"]}]}',
        "[1, 2]",
    ],
)
def test_parse_plan_rejects_invalid(payload):
    with pytest.raises(PlanValidationError):
        parse_plan(payload, "Objective")
