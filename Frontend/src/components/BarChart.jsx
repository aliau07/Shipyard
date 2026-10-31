import React from 'react';

export default function BarChart({ rows, format = value => value, emptyText = 'Nothing to show yet.', tone }) {
  const visible = rows.filter(row => Number(row.value) > 0 || rows.length <= 6);
  const max = Math.max(...visible.map(row => Number(row.value)), 0);
  if (max === 0) return <p className="muted">{emptyText}</p>;
  return (
    <ul className="bars">
      {visible.map(row => (
        <li key={row.key}>
          <span className="bar-label">{row.label}</span>
          <span className="bar-track">
            <span className={`bar-fill ${row.tone ?? tone ?? ''}`} style={{ width: `${(Number(row.value) / max) * 100}%` }} />
          </span>
          <span className="bar-value">{format(row.value)}</span>
        </li>
      ))}
    </ul>
  );
}
