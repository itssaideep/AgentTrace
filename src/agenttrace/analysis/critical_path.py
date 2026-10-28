"""Critical path solver via topological traversal and PERT/CPM forward/backward passes."""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any


@dataclass
class CriticalPathNode:
    """Node in the causal workflow graph with PERT/CPM timing bounds."""

    node_id: str
    duration_ns: int
    early_start_ns: int = 0
    early_finish_ns: int = 0
    late_start_ns: int = 0
    late_finish_ns: int = 0
    slack_ns: int = 0
    is_critical: bool = False

    @property
    def duration_ms(self) -> float:
        return self.duration_ns / 1_000_000.0

    @property
    def slack_ms(self) -> float:
        return self.slack_ns / 1_000_000.0


@dataclass
class CriticalPathResult:
    """Result of critical-path graph analysis."""

    critical_path: list[str]
    critical_path_duration_ns: int
    observed_makespan_ns: int
    critical_path_ratio: float
    nodes: dict[str, CriticalPathNode] = field(default_factory=dict)
    parallelism_potential: float = 1.0  # Total duration / Critical path duration

    @property
    def critical_path_duration_ms(self) -> float:
        return self.critical_path_duration_ns / 1_000_000.0

    @property
    def observed_makespan_ms(self) -> float:
        return self.observed_makespan_ns / 1_000_000.0


def compute_critical_path(
    nodes: dict[str, int],
    edges: list[tuple[str, str]],
    observed_makespan_ns: int | None = None,
) -> CriticalPathResult:
    """Compute the critical path through a DAG given node durations and dependency edges.

    Args:
        nodes: Mapping from node_id to duration in nanoseconds.
        edges: List of directed causal edges (predecessor, successor), meaning
               successor depends on predecessor.
        observed_makespan_ns: Actual trace makespan for ratio calculation. If None,
                              defaults to critical path duration.

    Returns:
        CriticalPathResult containing critical path sequence, slack metrics, and ratios.
    """
    if not nodes:
        return CriticalPathResult(
            critical_path=[],
            critical_path_duration_ns=0,
            observed_makespan_ns=observed_makespan_ns or 0,
            critical_path_ratio=0.0,
            nodes={},
            parallelism_potential=1.0,
        )

    # Build adjacency lists and compute in-degrees
    adj: dict[str, list[str]] = defaultdict(list)
    rev_adj: dict[str, list[str]] = defaultdict(list)
    in_degree: dict[str, int] = dict.fromkeys(nodes, 0)

    for u, v in edges:
        if u in nodes and v in nodes:
            adj[u].append(v)
            rev_adj[v].append(u)
            in_degree[v] += 1

    # Topological sort via Kahn's algorithm
    queue: deque[str] = deque([n for n, deg in in_degree.items() if deg == 0])
    topo_order: list[str] = []

    while queue:
        curr = queue.popleft()
        topo_order.append(curr)
        for succ in adj[curr]:
            in_degree[succ] -= 1
            if in_degree[succ] == 0:
                queue.append(succ)

    # Initialize CPM node tracking
    cpm_nodes: dict[str, CriticalPathNode] = {
        nid: CriticalPathNode(node_id=nid, duration_ns=nodes[nid]) for nid in nodes
    }

    # Forward pass: compute Early Start (ES) and Early Finish (EF)
    for u in topo_order:
        node_u = cpm_nodes[u]
        preds = rev_adj[u]
        if not preds:
            node_u.early_start_ns = 0
        else:
            node_u.early_start_ns = max(cpm_nodes[p].early_finish_ns for p in preds)
        node_u.early_finish_ns = node_u.early_start_ns + node_u.duration_ns

    # Makespan lower bound
    critical_makespan_ns = max(n.early_finish_ns for n in cpm_nodes.values())

    # Backward pass: compute Late Finish (LF) and Late Start (LS)
    for u in reversed(topo_order):
        node_u = cpm_nodes[u]
        succs = adj[u]
        if not succs:
            node_u.late_finish_ns = critical_makespan_ns
        else:
            node_u.late_finish_ns = min(cpm_nodes[s].late_start_ns for s in succs)
        node_u.late_start_ns = node_u.late_finish_ns - node_u.duration_ns
        node_u.slack_ns = node_u.late_start_ns - node_u.early_start_ns
        node_u.is_critical = node_u.slack_ns == 0

    # Trace critical path: walk from an initial 0-slack node to a sink along 0-slack edges
    critical_path: list[str] = []
    current_roots = [n for n in topo_order if cpm_nodes[n].is_critical and not rev_adj[n]]

    if current_roots:
        path_curr: str | None = current_roots[0]
        while path_curr:
            critical_path.append(path_curr)
            # Find critical successor with matching EF == succ.ES
            curr_ef = cpm_nodes[path_curr].early_finish_ns
            crit_succs = [
                s
                for s in adj[path_curr]
                if cpm_nodes[s].is_critical and cpm_nodes[s].early_start_ns == curr_ef
            ]
            path_curr = crit_succs[0] if crit_succs else None

    total_work_ns = sum(nodes.values())
    effective_makespan = observed_makespan_ns if observed_makespan_ns else critical_makespan_ns
    critical_ratio = (critical_makespan_ns / effective_makespan) if effective_makespan > 0 else 1.0
    parallelism_potential = (
        (total_work_ns / critical_makespan_ns) if critical_makespan_ns > 0 else 1.0
    )

    return CriticalPathResult(
        critical_path=critical_path,
        critical_path_duration_ns=critical_makespan_ns,
        observed_makespan_ns=effective_makespan,
        critical_path_ratio=min(1.0, critical_ratio),
        nodes=cpm_nodes,
        parallelism_potential=parallelism_potential,
    )


def compute_critical_path_from_spans(
    spans: list[dict[str, Any]],
    observed_makespan_ns: int | None = None,
) -> CriticalPathResult:
    """Compute critical path from a list of span dicts with explicit dependencies.

    Dependencies are extracted from 'depends_on' (list of span_ids) or 'parent_span_id'.
    """
    node_durations: dict[str, int] = {}
    edges: list[tuple[str, str]] = []

    for s in spans:
        span_id = str(s.get("span_id", ""))
        start_ns = (
            s.get("start_monotonic_ns")
            if s.get("start_monotonic_ns") is not None
            else s.get("start_ns")
        )
        end_ns = (
            s.get("end_monotonic_ns") if s.get("end_monotonic_ns") is not None else s.get("end_ns")
        )

        if start_ns is not None and end_ns is not None:
            node_durations[span_id] = max(0, int(end_ns) - int(start_ns))

        # Dependencies
        depends_on = s.get("depends_on") or s.get("attributes", {}).get("depends_on", [])
        if isinstance(depends_on, list):
            for dep in depends_on:
                edges.append((str(dep), span_id))

        parent_id = s.get("parent_span_id")
        if parent_id:
            # If explicit dependencies are not provided, child depends on parent
            if not depends_on:
                edges.append((str(parent_id), span_id))

    return compute_critical_path(node_durations, edges, observed_makespan_ns=observed_makespan_ns)
