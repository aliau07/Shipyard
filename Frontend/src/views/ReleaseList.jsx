import React from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import LoadState from '../components/LoadState';
import Pagination from '../components/Pagination';
import StatusTag from '../components/StatusTag';
import { STATUS_LABELS, formatDate } from '../format';
import { buildQuery, useApi, usePaginatedList } from '../hooks';

export default function ReleaseList() {
  const [params, setParams] = useSearchParams();
  const status = params.get('status') ?? '';
  const project = params.get('project') ?? '';
  const projects = useApi('/projects/?page_size=100');
  const { rows, count, page, setPage, loading, error } = usePaginatedList(`/releases/${buildQuery({ status, project })}`);

  const setFilter = (name, value) => {
    const next = new URLSearchParams(params);
    if (value) next.set(name, value); else next.delete(name);
    setParams(next);
  };

  return (
    <div>
      <div className="page-header">
        <h2>Releases</h2>
        <Link className="button" to="/releases/new">New release</Link>
      </div>
      <div className="filters">
        <label className="inline-label">Status
          <select value={status} onChange={e => setFilter('status', e.target.value)}>
            <option value="">All</option>
            {Object.entries(STATUS_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select>
        </label>
        <label className="inline-label">Project
          <select value={project} onChange={e => setFilter('project', e.target.value)}>
            <option value="">All</option>
            {(projects.data?.results ?? []).map(item => <option key={item.id} value={item.id}>{item.name}</option>)}
          </select>
        </label>
      </div>
      <LoadState loading={loading && rows.length === 0} error={error}>
        {rows.length === 0 ? <p className="muted">No releases match.</p> : (
          <div className="table-wrap">
            <table>
              <thead><tr><th>Release</th><th>Project</th><th>Version</th><th>Status</th><th>Changes</th><th>Target</th></tr></thead>
              <tbody>
                {rows.map(release => (
                  <tr key={release.id} className={release.status === 'cancelled' ? 'row-muted' : ''}>
                    <td><span className="ref">{release.reference}</span> <Link className="ticket-link" to={`/releases/${release.id}`}>{release.title}</Link></td>
                    <td>{release.project_name}</td>
                    <td className="mono">{release.version}</td>
                    <td><StatusTag status={release.status} /></td>
                    <td>{release.change_count}</td>
                    <td>{formatDate(release.target_date)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <Pagination page={page} count={count} onChange={setPage} />
      </LoadState>
    </div>
  );
}
