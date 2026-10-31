import React, { useState } from 'react';
import { KIND_LABELS, formatMinutes, pathText } from '../format';
import { NODE_H, NODE_W, PAD, cycleEdgeKeys, edgeKey, edgePath, impactHighlight, layoutGraph } from '../graphLayout';

function columnTitle(graph, column) {
  const blockedColumn = graph.blocked && graph.blocked.length > 0 && column === graph.layers.length - 1;
  return blockedColumn ? 'Blocked by cycle' : `Wave ${column + 1}`;
}

function shorten(name) {
  return name.length > 20 ? `${name.slice(0, 19)}…` : name;
}

export default function GraphView({ graph, title = 'Dependency graph', emptyText = 'No components yet.' }) {
  const [selected, setSelected] = useState(null);
  if (!graph || graph.nodes.length === 0) return <p className="muted">{emptyText}</p>;

  const { positions, width, height } = layoutGraph(graph);
  const cycleEdges = cycleEdgeKeys(graph.cycle);
  const impacted = impactHighlight(graph.impact, selected);
  const impactList = selected && graph.impact ? graph.impact[selected] || [] : [];
  const toggle = name => setSelected(current => (current === name ? null : name));

  const edgeClass = edge => {
    const key = edgeKey(edge.from, edge.to);
    if (cycleEdges.has(key)) return 'edge edge-cycle';
    if (impacted.edges.has(key)) return 'edge edge-impact';
    return 'edge';
  };
  const nodeClass = node => {
    const classes = ['node', `node-${node.kind}`];
    if (node.in_cycle) classes.push('node-cycle');
    if (node.name === selected) classes.push('node-selected');
    if (impacted.nodes.has(node.name)) classes.push('node-impacted');
    return classes.join(' ');
  };

  return (
    <figure className="graph">
      <div className="graph-scroll">
        <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} role="img"
             aria-label={`${title}: ${graph.nodes.length} components in ${graph.layers.length} columns${graph.cycle ? ', with a dependency cycle' : ''}`}>
          <defs>
            <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
              <path d="M 0 0 L 10 5 L 0 10 z" className="arrow-head" />
            </marker>
            <marker id="arrow-cycle" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
              <path d="M 0 0 L 10 5 L 0 10 z" className="arrow-head cycle" />
            </marker>
            <marker id="arrow-impact" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
              <path d="M 0 0 L 10 5 L 0 10 z" className="arrow-head impact" />
            </marker>
          </defs>
          {graph.layers.map((layer, column) => (
            <text key={`col${column}`} className="graph-column-title" x={positions[layer[0]].x} y={PAD + 14}>
              {columnTitle(graph, column)}
            </text>
          ))}
          {graph.edges.map(edge => {
            const className = edgeClass(edge);
            const marker = className.includes('cycle') ? 'arrow-cycle' : className.includes('impact') ? 'arrow-impact' : 'arrow';
            return (
              <path key={edgeKey(edge.from, edge.to)} data-testid={`edge-${edge.to}-${edge.from}`} className={className}
                    d={edgePath(positions[edge.to], positions[edge.from])} markerEnd={`url(#${marker})`} />
            );
          })}
          {graph.nodes.map(node => {
            const { x, y } = positions[node.name];
            return (
              <g key={node.name} className={nodeClass(node)} data-testid={`node-${node.name}`} role="button" tabIndex={0}
                 aria-pressed={node.name === selected}
                 aria-label={`${node.name}, ${KIND_LABELS[node.kind] ?? node.kind}${node.in_cycle ? ', on a dependency cycle' : ''}`}
                 onClick={() => toggle(node.name)}
                 onKeyDown={event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); toggle(node.name); } }}>
                <title>{`${node.name} (${KIND_LABELS[node.kind] ?? node.kind}), ${formatMinutes(node.deploy_minutes)}${node.owner_name ? `, owned by ${node.owner_name}` : ''}`}</title>
                <rect x={x} y={y} width={NODE_W} height={NODE_H} rx="4" />
                <text x={x + 10} y={y + 19} className="node-name">{shorten(node.name)}</text>
                <text x={x + 10} y={y + 37} className="node-meta">{KIND_LABELS[node.kind] ?? node.kind} · {formatMinutes(node.deploy_minutes)}</text>
              </g>
            );
          })}
        </svg>
      </div>
      <figcaption className="graph-legend small">
        <span>Arrows run from a dependency to what depends on it, in deploy order. Select a component to trace its impact.</span>
        {graph.cycle && <span className="legend-cycle" role="alert">Cycle: {pathText(graph.cycle)}</span>}
      </figcaption>
      {selected && (
        <div className="impact-list" aria-live="polite">
          <h4>Impact of {selected}</h4>
          {impactList.length === 0 ? <p className="muted">Nothing depends on {selected}.</p> : (
            <ul>
              {impactList.map(entry => (
                <li key={entry.name}>
                  <strong>{entry.name}</strong> <span className="muted small">{pathText(entry.path)}</span>
                  {entry.in_view === false && <span className="tag">not in this release</span>}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </figure>
  );
}
