import React from 'react';
import { formatMinutes, pathText } from '../format';

export default function WavePlan({ plan }) {
  if (!plan || plan.nodes.length === 0) return <p className="muted">Add component changes to see the deploy plan.</p>;
  if (!plan.waves) {
    return (
      <div className="notice" role="alert">
        <strong>No deploy order is possible.</strong> These components depend on each other in a cycle:{' '}
        <span className="mono">{pathText(plan.cycle)}</span>. Break the cycle to get release waves.
      </div>
    );
  }
  const minutes = {};
  for (const node of plan.nodes) minutes[node.name] = node.deploy_minutes;
  const critical = new Set(plan.critical_path ? plan.critical_path.path : []);
  return (
    <div>
      <ol className="waves">
        {plan.waves.map((wave, index) => {
          let longest = 0;
          for (const name of wave) longest = Math.max(longest, minutes[name]);
          return (
            <li key={wave.join()}>
              <span className="wave-label">Wave {index + 1}</span>
              <span className="tags">
                {wave.map(name => <span key={name} className={`tag ${critical.has(name) ? 'tag-critical' : ''}`}>{name}</span>)}
              </span>
              <span className="muted small">{formatMinutes(longest)}</span>
            </li>
          );
        })}
      </ol>
      <dl className="kv">
        <dt>Critical path</dt>
        <dd>{pathText(plan.critical_path.path)} ({formatMinutes(plan.critical_path.minutes)})</dd>
        <dt>Wave by wave</dt>
        <dd>{formatMinutes(plan.estimated_minutes)}</dd>
        {plan.unchanged_dependents && plan.unchanged_dependents.length > 0 && (<>
          <dt>Also affected</dt><dd>{plan.unchanged_dependents.join(', ')}</dd>
        </>)}
      </dl>
    </div>
  );
}
