import React from 'react';
import { PAGE_SIZE } from '../hooks';

export default function Pagination({ page, count, onChange }) {
  const pages = Math.max(1, Math.ceil(count / PAGE_SIZE));
  if (pages === 1) return null;
  return (
    <div className="pagination">
      <button type="button" className="secondary" onClick={() => onChange(page - 1)} disabled={page <= 1}>Previous</button>
      <span>Page {page} of {pages}</span>
      <button type="button" className="secondary" onClick={() => onChange(page + 1)} disabled={page >= pages}>Next</button>
    </div>
  );
}
