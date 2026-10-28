"""Unit tests for critical path solver and PERT/CPM calculations."""

from agenttrace.analysis.critical_path import (
    compute_critical_path,
    compute_critical_path_from_spans,
)


def test_critical_path_linear_chain() -> None:
    # Linear chain A (10) -> B (20) -> C (30)
    # Total duration = 60
    nodes = {"A": 10, "B": 20, "C": 30}
    edges = [("A", "B"), ("B", "C")]

    res = compute_critical_path(nodes, edges)
    assert res.critical_path == ["A", "B", "C"]
    assert res.critical_path_duration_ns == 60
    assert res.critical_path_ratio == 1.0
    assert res.parallelism_potential == 1.0

    for n in ["A", "B", "C"]:
        assert res.nodes[n].slack_ns == 0
        assert res.nodes[n].is_critical is True


def test_critical_path_diamond_graph() -> None:
    # Diamond graph:
    #      B (20)
    #    /        \
    # A(10)        D (10)
    #    \        /
    #      C (50)
    #
    # Path A -> B -> D duration: 10 + 20 + 10 = 40
    # Path A -> C -> D duration: 10 + 50 + 10 = 70
    # Critical path: A -> C -> D (duration 70)
    # B early_start: 10, early_finish: 30
    # D late_start: 60 -> B late_finish: 60 -> B late_start: 40 -> slack: 40 - 10 = 30
    nodes = {"A": 10, "B": 20, "C": 50, "D": 10}
    edges = [("A", "B"), ("A", "C"), ("B", "D"), ("C", "D")]

    res = compute_critical_path(nodes, edges)
    assert res.critical_path == ["A", "C", "D"]
    assert res.critical_path_duration_ns == 70
    assert res.nodes["B"].slack_ns == 30
    assert res.nodes["B"].is_critical is False
    assert res.nodes["C"].slack_ns == 0
    assert res.nodes["C"].is_critical is True
    # Parallelism potential: (10 + 20 + 50 + 10) / 70 = 90 / 70 = 1.2857
    assert abs(res.parallelism_potential - (90.0 / 70.0)) < 1e-4


def test_critical_path_from_spans() -> None:
    spans = [
        {"span_id": "root", "start_ns": 0, "end_ns": 100, "depends_on": []},
        {"span_id": "branch_1", "start_ns": 100, "end_ns": 300, "depends_on": ["root"]},
        {"span_id": "branch_2", "start_ns": 100, "end_ns": 150, "depends_on": ["root"]},
        {"span_id": "join", "start_ns": 300, "end_ns": 400, "depends_on": ["branch_1", "branch_2"]},
    ]

    res = compute_critical_path_from_spans(spans, observed_makespan_ns=400)
    assert res.critical_path == ["root", "branch_1", "join"]
    assert res.critical_path_duration_ns == 400
    assert res.critical_path_ratio == 1.0
