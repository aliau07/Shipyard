import React from 'react';
import { Link } from 'react-router-dom';
import BarChart from '../components/BarChart';
import LoadState from '../components/LoadState';
import StatusTag from '../components/StatusTag';
import { formatDate, formatDateTime } from '../format';
import { useApi } from '../hooks';

function Stat({ label, value, to }) {
  const content = <><span className="stat-value">{value ?? '–'}</span><span className="stat-label">{label}</span></>;
  return to ? <Link className="stat card card-link" to={to}>{content}</Link> : <div className="stat card">{content}</div>;
}

export default function Dashboard() {
  const { data, loading, error } = useApi('/dashboard/');
  return (
    <div>
      <div className="page-header">
        <h2>Dashboard</h2>
        <Link className="button" to="/releases/new">New release</Link>
      </div>
      <LoadState loading={loading} error={error}>
        {data && (<>
          <div className="stats">
            <Stat label="Open releases" value={data.summary.open} to="/releases" />
            <Stat label="In review" value={data.summary.in_review} to="/releases?status=in_review" />
            <Stat label="Blocked" value={data.summary.blocked} to="/releases?status=blocked" />
            <Stat label={`Released in ${data.summary.recent_days} days`} value={data.summary.released_recently} />
            <Stat label="Average waves per release" value={data.waves.average} />
          </div>
          <div className="grid">
            <section className="card">
              <h3>Releases by status</h3>
              <BarChart rows={data.by_status.map(row => ({ key: row.key, label: row.label, value: row.count }))} emptyText="No releases yet." />
            </section>
            <section className="card">
              <h3>Most depended-on components</h3>
              <BarChart rows={data.most_depended_on.map(row => ({ key: row.id, label: `${row.name} (${row.project_name})`, value: row.dependents }))}
                        emptyText="No dependencies recorded yet." />
              <p className="muted small">A change to these touches the most other components.</p>
            </section>
          </div>
          <div className="grid">
            <section className="card">
              <h3>Blocked releases</h3>
              {data.blocked_releases.length === 0 ? <p className="muted">Nothing is blocked.</p> : (
                <ul className="mini-list">
                  {data.blocked_releases.map(release => (
                    <li key={release.id}>
                      <Link to={`/releases/${release.id}`}>{release.title}</Link>
                      <span className="muted small">{release.project_name} {release.version}</span>
                      <span className="block small">{release.blocked_reason}</span>
                      <span className="muted small">since {formatDateTime(release.updated_at)}</span>
                    </li>
                  ))}
                </ul>
              )}
            </section>
            <section className="card">
              <h3>Coming up</h3>
              {data.upcoming_releases.length === 0 ? <p className="muted">No target dates set.</p> : (
                <ul className="mini-list">
                  {data.upcoming_releases.map(release => (
                    <li key={release.id}>
                      <Link to={`/releases/${release.id}`}>{release.title}</Link>
                      <span className="muted small">{release.version} · {formatDate(release.target_date)}</span>
                      <span className="mini-badges"><StatusTag status={release.status} /></span>
                    </li>
                  ))}
                </ul>
              )}
              {data.waves.with_cycles > 0 && (
                <p className="error small">{data.waves.with_cycles} release{data.waves.with_cycles === 1 ? ' has' : 's have'} a dependency cycle.</p>
              )}
            </section>
          </div>
        </>)}
      </LoadState>
    </div>
  );
}
