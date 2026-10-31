import React, { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { apiDelete, apiPost, downloadFile, fetchAll } from '../api';
import ActionPanel from '../components/ActionPanel';
import GraphView from '../components/GraphView';
import Icon from '../components/Icon';
import LoadState from '../components/LoadState';
import StatusTag from '../components/StatusTag';
import { CommentForm, Timeline } from '../components/Timeline';
import WavePlan from '../components/WavePlan';
import { CHANGE_TYPE_LABELS, errorMessages, formatDate, formatDateTime, roleLabel } from '../format';
import { useApi } from '../hooks';

function AddChange({ release, onAdded }) {
  const [components, setComponents] = useState([]);
  const [values, setValues] = useState({ component: '', summary: '', change_type: 'feature' });
  const [errors, setErrors] = useState([]);

  useEffect(() => {
    fetchAll(`/components/?project=${release.project}`).then(setComponents).catch(() => setComponents([]));
  }, [release.project]);

  const used = new Set();
  for (const change of release.changes) used.add(change.component);
  const available = components.filter(component => !used.has(component.id));

  async function submit(event) {
    event.preventDefault();
    setErrors([]);
    try {
      await apiPost(`/releases/${release.id}/changes/`, { ...values, component: Number(values.component) });
      setValues({ component: '', summary: '', change_type: 'feature' });
      onAdded();
    } catch (error) {
      setErrors(errorMessages(error));
    }
  }

  return (
    <form className="inline-form add-change" onSubmit={submit}>
      <select aria-label="Component" value={values.component} onChange={e => setValues({ ...values, component: e.target.value })} required>
        <option value="">Add a component</option>
        {available.map(component => <option key={component.id} value={component.id}>{component.name}</option>)}
      </select>
      <input aria-label="Summary" placeholder="What changes?" value={values.summary} onChange={e => setValues({ ...values, summary: e.target.value })} required />
      <select aria-label="Change type" value={values.change_type} onChange={e => setValues({ ...values, change_type: e.target.value })}>
        {Object.entries(CHANGE_TYPE_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
      </select>
      <button type="submit" className="secondary small">Add</button>
      {errors.map(message => <p key={message} className="error" role="alert">{message}</p>)}
    </form>
  );
}

function Changes({ release, onChanged }) {
  const [errors, setErrors] = useState([]);
  const signed = {};
  for (const signOff of release.sign_offs) signed[signOff.component] = signOff;
  const editable = release.status === 'draft' && release.viewer_role;

  async function remove(change) {
    setErrors([]);
    try {
      await apiDelete(`/releases/${release.id}/changes/${change.id}/`);
      onChanged();
    } catch (error) {
      setErrors(errorMessages(error));
    }
  }

  return (
    <section className="card">
      <h3>Changes and sign-offs</h3>
      {release.changes.length === 0 ? <p className="muted">No component changes yet.</p> : (
        <div className="table-wrap">
          <table className="dense">
            <thead><tr><th>Component</th><th>Change</th><th>Owner</th><th>Sign-off</th>{editable && <th><span className="visually-hidden">Remove</span></th>}</tr></thead>
            <tbody>
              {release.changes.map(change => {
                const signOff = signed[change.component];
                return (
                  <tr key={change.id}>
                    <td><strong>{change.component_name}</strong></td>
                    <td><span className={`tag ${change.change_type === 'breaking' ? 'tag-critical' : ''}`}>{change.change_type_display}</span> {change.summary}</td>
                    <td>{change.owner_name ?? <span className="muted">release managers</span>}</td>
                    <td>{signOff
                      ? <span className="success-text"><Icon name="badge-check" size={14} /> {signOff.user_name}</span>
                      : <span className="muted">waiting</span>}</td>
                    {editable && <td><button type="button" className="link danger-text" onClick={() => remove(change)}>Remove</button></td>}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      {editable && <AddChange release={release} onAdded={onChanged} />}
      {errors.map(message => <p key={message} className="error" role="alert">{message}</p>)}
    </section>
  );
}

export default function ReleaseDetail() {
  const { id } = useParams();
  const { data: release, loading, error, reload } = useApi(`/releases/${id}/`);
  const [exportError, setExportError] = useState(null);

  async function exportPlan() {
    setExportError(null);
    try {
      await downloadFile(`/releases/${id}/export/`, `release-plan-${id}.csv`);
    } catch (problem) {
      setExportError(errorMessages(problem).join(' '));
    }
  }

  return (
    <LoadState loading={loading && !release} error={error}>
      {release && (
        <div>
          <div className="ticket-header page-header">
            <div>
              <p className="muted small"><Link to={`/projects/${release.project}`}>{release.project_name}</Link> · <span className="ref">{release.reference}</span></p>
              <h2>{release.title} <span className="mono version">{release.version}</span></h2>
              <div className="actions">
                <StatusTag status={release.status} />
                {release.target_date && <span className="muted small">Target {formatDate(release.target_date)}</span>}
                {release.viewer_role && <span className="muted small">You are {roleLabel(release.viewer_role).toLowerCase()}</span>}
              </div>
            </div>
            <button type="button" className="secondary" onClick={exportPlan}><Icon name="download" />Export plan (CSV)</button>
          </div>
          {exportError && <p className="error" role="alert">{exportError}</p>}
          <div className="detail-grid">
            <div>
              <section className="card">
                <h3>Deploy plan</h3>
                <GraphView graph={release.plan} title="Release plan" emptyText="Add component changes to see the plan." />
                <WavePlan plan={release.plan} />
              </section>
              <Changes release={release} onChanged={reload} />
              <section className="card">
                <h3>Timeline</h3>
                <Timeline items={release.timeline} />
                <CommentForm release={release} onPosted={reload} />
              </section>
            </div>
            <div>
              <ActionPanel release={release} onChanged={reload} />
              <section className="card">
                <h3>Details</h3>
                {release.description && <p className="prewrap">{release.description}</p>}
                <dl className="kv">
                  <dt>Created by</dt><dd>{release.created_by_name}</dd>
                  <dt>Updated</dt><dd>{formatDateTime(release.updated_at)}</dd>
                  {release.approved_at && <><dt>Approved</dt><dd>{formatDateTime(release.approved_at)}</dd></>}
                  {release.released_at && <><dt>Released</dt><dd>{formatDateTime(release.released_at)}</dd></>}
                  {release.reopen_count > 0 && <><dt>Reopened</dt><dd>{release.reopen_count}×</dd></>}
                </dl>
              </section>
            </div>
          </div>
        </div>
      )}
    </LoadState>
  );
}
