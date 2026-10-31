import React from 'react';
import ICONS from '../icons/lucide';

export default function Icon({ name, label, size = 18, filled = false, className = '' }) {
  const nodes = ICONS[name];
  if (!nodes) throw new Error(`Unknown icon "${name}"`);
  const a11y = label ? { role: 'img', 'aria-label': label } : { 'aria-hidden': 'true', focusable: 'false' };
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill={filled ? 'currentColor' : 'none'}
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={`icon ${className}`.trim()}
      {...a11y}
    >
      {nodes.map(([tag, attributes], index) => React.createElement(tag, { key: index, ...attributes }))}
    </svg>
  );
}
