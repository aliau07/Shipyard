// Geometry for the dependency graph view: one column per release wave, nodes stacked by name.
// Edges come from the API as { from: dependent, to: dependency }; arrows are drawn from the dependency to the
// dependent, i.e. in deploy order and in the direction a change ripples.

export const NODE_W = 168;
export const NODE_H = 48;
export const COL_GAP = 72;
export const ROW_GAP = 16;
export const PAD = 16;
export const HEADER = 28;

export function layoutGraph(graph) {
  const positions = {};
  let rows = 0;
  graph.layers.forEach((layer, column) => {
    layer.forEach((name, row) => {
      positions[name] = { x: PAD + column * (NODE_W + COL_GAP), y: PAD + HEADER + row * (NODE_H + ROW_GAP), column };
    });
    rows = Math.max(rows, layer.length);
  });
  const columns = Math.max(graph.layers.length, 1);
  return {
    positions,
    width: PAD * 2 + columns * NODE_W + (columns - 1) * COL_GAP,
    height: PAD * 2 + HEADER + Math.max(rows, 1) * NODE_H + Math.max(rows - 1, 0) * ROW_GAP,
  };
}

export const edgeKey = (dependent, dependency) => `${dependent}->${dependency}`;

export function cycleEdgeKeys(cycle) {
  const keys = new Set();
  if (!cycle) return keys;
  for (let index = 0; index < cycle.length - 1; index += 1) keys.add(edgeKey(cycle[index], cycle[index + 1]));
  return keys;
}

// The nodes and edges on the impact paths of `selected`. A path [a, b, c] means b depends on a and c on b.
export function impactHighlight(impact, selected) {
  const nodes = new Set();
  const edges = new Set();
  if (!selected || !impact || !impact[selected]) return { nodes, edges };
  for (const entry of impact[selected]) {
    nodes.add(entry.name);
    for (let index = 0; index < entry.path.length - 1; index += 1) {
      edges.add(edgeKey(entry.path[index + 1], entry.path[index]));
    }
  }
  return { nodes, edges };
}

// A curve from the right edge of the dependency to the left edge of the dependent. Edges that point backwards
// (only possible on a cycle) loop around below the nodes so they stay visible.
export function edgePath(dependency, dependent) {
  const startX = dependency.x + NODE_W;
  const startY = dependency.y + NODE_H / 2;
  const endX = dependent.x;
  const endY = dependent.y + NODE_H / 2;
  if (endX > startX) {
    const bend = (endX - startX) / 2;
    return `M ${startX} ${startY} C ${startX + bend} ${startY}, ${endX - bend} ${endY}, ${endX} ${endY}`;
  }
  const drop = Math.max(startY, endY) + NODE_H;
  return `M ${startX} ${startY} C ${startX + COL_GAP} ${drop}, ${endX - COL_GAP} ${drop}, ${endX} ${endY}`;
}
