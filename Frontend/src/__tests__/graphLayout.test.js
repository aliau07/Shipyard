import { COL_GAP, NODE_W, cycleEdgeKeys, edgePath, impactHighlight, layoutGraph } from '../graphLayout';
import { sampleGraph } from '../testUtils';

test('one column per wave, nodes stacked in order', () => {
  const { positions, width, height } = layoutGraph(sampleGraph());

  expect(positions.models.x).toBe(positions.ui.x);
  expect(positions.ui.y).toBeGreaterThan(positions.models.y);
  expect(positions.api.x - positions.models.x).toBe(NODE_W + COL_GAP);
  expect(positions.web.column).toBe(2);
  expect(width).toBeGreaterThan(positions.web.x + NODE_W);
  expect(height).toBeGreaterThan(positions.ui.y);
});

test('cycle paths become edge keys', () => {
  expect([...cycleEdgeKeys(['a', 'b', 'a'])]).toEqual(['a->b', 'b->a']);
  expect(cycleEdgeKeys(null).size).toBe(0);
});

test('impact paths highlight every edge on the way', () => {
  const { nodes, edges } = impactHighlight(sampleGraph().impact, 'models');
  expect([...nodes]).toEqual(['api', 'worker', 'web']);
  expect([...edges].sort()).toEqual(['api->models', 'web->api', 'worker->models']);
  expect(impactHighlight(sampleGraph().impact, null).nodes.size).toBe(0);
});

test('forward edges curve to the right; backward edges loop underneath', () => {
  const left = { x: 0, y: 0 };
  const right = { x: 300, y: 0 };
  expect(edgePath(left, right).startsWith(`M ${NODE_W} 24 C`)).toBe(true);
  expect(edgePath(right, left)).toContain(`${300 + NODE_W + COL_GAP} 72`);
});
