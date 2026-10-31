"""Dependency graph algorithms for release planning.

Pure Python with no Django imports, so it can be tested and reused on its own.

A graph maps a node name to the names it depends on: ``{'web': ['api'], 'api': []}`` means ``web`` depends on
``api``, so ``api`` has to be deployed first. Names that only appear as dependencies are treated as nodes with
no dependencies of their own. Every function breaks ties by node name, so the same input always gives the same
output.
"""
import heapq
from collections import deque


class CycleError(ValueError):
    """An ordering was asked for but the graph has a cycle. `cycle` holds the path, e.g. ['a', 'b', 'a']."""

    def __init__(self, cycle):
        super().__init__('Dependency cycle: ' + ' -> '.join(cycle))
        self.cycle = cycle


def build_graph(nodes, edges):
    """Make a graph from node names and (dependent, dependency) pairs.

    Every node becomes a key with a sorted, de-duplicated dependency list. An edge naming an unknown node raises
    ValueError.
    """
    found = {}
    for node in nodes:
        found[node] = set()
    for dependent, dependency in edges:
        if dependent not in found or dependency not in found:
            raise ValueError(f'Edge {dependent!r} -> {dependency!r} names an unknown node.')
        found[dependent].add(dependency)
    graph = {}
    for node in sorted(found):
        graph[node] = sorted(found[node])
    return graph


def _normalize(graph):
    """A copy of `graph` where every node is a key and dependency lists are sorted and unique."""
    nodes = set(graph)
    for dependencies in graph.values():
        nodes.update(dependencies)
    result = {}
    for node in sorted(nodes):
        result[node] = sorted(set(graph.get(node, ())))
    return result


def dependents_of(graph):
    """The reverse graph: for every node, the sorted nodes that depend on it."""
    graph = _normalize(graph)
    reverse = {}
    for node in graph:
        reverse[node] = []
    for node in graph:
        for dependency in graph[node]:
            reverse[dependency].append(node)
    for node in reverse:
        reverse[node].sort()
    return reverse


def find_cycle(graph):
    """Return a cycle as a path that starts and ends on the same node, or None when there is none.

    The path follows dependency edges: ['a', 'b', 'a'] means a depends on b and b depends on a. Nodes and their
    dependencies are explored in name order (depth first, without recursion), so the answer is deterministic.
    """
    graph = _normalize(graph)
    unvisited, in_progress, finished = 0, 1, 2
    state = dict.fromkeys(graph, unvisited)
    for root in graph:
        if state[root] != unvisited:
            continue
        state[root] = in_progress
        path = [root]
        stack = [iter(graph[root])]
        while stack:
            moved = False
            for dependency in stack[-1]:
                if state[dependency] == in_progress:
                    start = path.index(dependency)
                    return path[start:] + [dependency]
                if state[dependency] == unvisited:
                    state[dependency] = in_progress
                    path.append(dependency)
                    stack.append(iter(graph[dependency]))
                    moved = True
                    break
            if not moved:
                state[path.pop()] = finished
                stack.pop()
    return None


def topological_order(graph):
    """Every node after all of its dependencies; among nodes that are ready at the same time, by name.

    Raises CycleError (with the cycle path) if no such order exists.
    """
    graph = _normalize(graph)
    reverse = dependents_of(graph)
    waiting_on = {}
    ready = []
    for node in graph:
        waiting_on[node] = len(graph[node])
        if waiting_on[node] == 0:
            ready.append(node)
    heapq.heapify(ready)
    order = []
    while ready:
        node = heapq.heappop(ready)
        order.append(node)
        for dependent in reverse[node]:
            waiting_on[dependent] -= 1
            if waiting_on[dependent] == 0:
                heapq.heappush(ready, dependent)
    if len(order) < len(graph):
        raise CycleError(find_cycle(graph))
    return order


def layers(graph):
    """Layered Kahn's algorithm. Returns (waves, blocked).

    waves[0] holds the nodes with no dependencies and waves[n] the nodes whose dependencies are all in earlier
    waves, each wave sorted by name. Nodes in the same wave can be deployed in parallel. `blocked` lists, by
    name, the nodes that never become ready because they are on a cycle or depend on one.
    """
    graph = _normalize(graph)
    reverse = dependents_of(graph)
    waiting_on = {}
    current = []
    for node in graph:
        waiting_on[node] = len(graph[node])
        if waiting_on[node] == 0:
            current.append(node)
    waves = []
    while current:
        waves.append(current)
        upcoming = []
        for node in current:
            for dependent in reverse[node]:
                waiting_on[dependent] -= 1
                if waiting_on[dependent] == 0:
                    upcoming.append(dependent)
        current = sorted(upcoming)
    blocked = []
    for node in graph:
        if waiting_on[node] > 0:
            blocked.append(node)
    return waves, blocked


def waves(graph):
    """The release waves (see `layers`). Raises CycleError when some nodes can never be deployed."""
    found, blocked = layers(graph)
    if blocked:
        raise CycleError(find_cycle(graph))
    return found


def critical_path(graph, weights):
    """The chain of dependencies with the largest total weight, such as deploy minutes.

    Returns (total, path) with the path in deploy order, starting from a node with no dependencies. However many
    deploys run in parallel, the release can't finish faster than this. Nodes missing from `weights` weigh 0 and
    negative weights raise ValueError. When chains tie, the one whose names sort first wins. Raises CycleError
    for graphs with a cycle.
    """
    graph = _normalize(graph)
    for node in graph:
        if weights.get(node, 0) < 0:
            raise ValueError(f'Weight of {node!r} must not be negative.')
    best = {}
    for node in topological_order(graph):
        chosen = None
        for dependency in graph[node]:
            total, path = best[dependency]
            if chosen is None or total > chosen[0] or (total == chosen[0] and path < chosen[1]):
                chosen = (total, path)
        if chosen is None:
            chosen = (0, [])
        best[node] = (chosen[0] + weights.get(node, 0), chosen[1] + [node])
    result = (0, [])
    for node in sorted(best):
        total, path = best[node]
        if not result[1] or total > result[0] or (total == result[0] and path < result[1]):
            result = (total, path)
    return result


def impact(graph, start):
    """Everything that depends on `start`, directly or through other nodes, with the path that reaches it.

    Returns a list of {'node', 'depth', 'path'} sorted by depth and then name, where `path` runs from `start` to
    the dependent. The search is breadth first over dependents in name order, so each path is a shortest one and
    ties go to names that sort first. Graphs with cycles are fine: each node is reported once and `start` never.
    """
    graph = _normalize(graph)
    if start not in graph:
        raise ValueError(f'Unknown node {start!r}.')
    reverse = dependents_of(graph)
    paths = {start: [start]}
    queue = deque([start])
    found = []
    while queue:
        node = queue.popleft()
        for dependent in reverse[node]:
            if dependent in paths:
                continue
            paths[dependent] = paths[node] + [dependent]
            found.append((len(paths[dependent]) - 1, dependent))
            queue.append(dependent)
    found.sort()
    results = []
    for depth, node in found:
        results.append({'node': node, 'depth': depth, 'path': paths[node]})
    return results


def contract(graph, keep):
    """The graph restricted to the nodes in `keep`, keeping indirect dependencies.

    In the result, a depends on b when it does directly or through nodes outside `keep`. That is what ordering a
    release needs: if web reaches api only through an unchanged gateway, the new web still waits for the new api.
    Paths that lead back to their own start through nodes outside `keep` are ignored.
    """
    graph = _normalize(graph)
    keep = set(keep)
    result = {}
    for node in sorted(keep):
        reached = set()
        seen = {node}
        stack = list(graph.get(node, ()))
        while stack:
            current = stack.pop()
            if current in seen:
                continue
            seen.add(current)
            if current in keep:
                reached.add(current)
            else:
                stack.extend(graph.get(current, ()))
        result[node] = sorted(reached)
    return result


def cycle_edges(cycle):
    """The (dependent, dependency) pairs along a cycle path."""
    edges = []
    if not cycle:
        return edges
    for index in range(len(cycle) - 1):
        edges.append((cycle[index], cycle[index + 1]))
    return edges
