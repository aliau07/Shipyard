import React, { useState } from 'react';
import { apiPost } from '../api';
import { errorMessages } from '../format';

const FIELD_LABELS = { note: 'Note (optional)', reason: 'Reason' };
const REQUIRED_FIELDS = new Set(['reason']);
const SECONDARY_ACTIONS = new Set(['cancel', 'block', 'request_changes', 'reopen']);

function ActionForm({ release, action, onDone, onCancel }) {
  const [values, setValues] = useState({});
  const [errors, setErrors] = useState([]);
  const [saving, setSaving] = useState(false);

  async function submit(event) {
    event.preventDefault();
    setSaving(true);
    setErrors([]);
    const payload = { action: action.name };
    for (const field of action.fields) {
      if (values[field]) payload[field] = values[field];
    }
    try {
      await apiPost(`/releases/${release.id}/transition/`, payload);
      onDone();
    } catch (error) {
      setErrors(errorMessages(error));
      setSaving(false);
    }
  }

  return (
    <form className="action-form" onSubmit={submit}>
      <h4>{action.label}</h4>
      {action.fields.map(field => (
        <label key={field}>{FIELD_LABELS[field] ?? field}
          <textarea rows={3} value={values[field] ?? ''} required={REQUIRED_FIELDS.has(field)}
                    onChange={event => setValues(previous => ({ ...previous, [field]: event.target.value }))} />
        </label>
      ))}
      {errors.map(message => <p key={message} className="error" role="alert">{message}</p>)}
      <div className="actions">
        <button type="submit" disabled={saving}>{saving ? 'Saving...' : action.label}</button>
        <button type="button" className="secondary" onClick={onCancel}>Back</button>
      </div>
    </form>
  );
}

function waitingNote(release) {
  if (release.status === 'in_progress') return 'Deploy the waves in order, then mark the release as released.';
  if (release.status === 'blocked' && release.blocked_reason) return `Blocked: ${release.blocked_reason}`;
  return null;
}

export default function ActionPanel({ release, onChanged, title = 'Next steps' }) {
  const [active, setActive] = useState(null);
  const [errors, setErrors] = useState([]);
  const actions = release.allowed_actions;
  const blockers = release.status === 'in_review' ? release.approval?.blockers ?? [] : [];
  const note = waitingNote(release);

  async function runDirect(action) {
    setErrors([]);
    try {
      await apiPost(`/releases/${release.id}/transition/`, { action: action.name });
      onChanged();
    } catch (error) {
      setErrors(errorMessages(error));
    }
  }

  const current = actions.find(action => action.name === active);
  const primary = actions.find(action => !SECONDARY_ACTIONS.has(action.name));
  return (
    <section className="card">
      <h3>{title}</h3>
      {note && !current && <p>{note}</p>}
      {blockers.length > 0 && !current && (
        <div className="notice approval-blockers">
          <strong>Can't approve yet</strong>
          <ul>{blockers.map(text => <li key={text}>{text}</li>)}</ul>
        </div>
      )}
      {actions.length === 0 && <p className="muted">Nothing for you to do right now.</p>}
      {current ? (
        <ActionForm release={release} action={current} onCancel={() => setActive(null)}
                    onDone={() => { setActive(null); onChanged(); }} />
      ) : actions.length > 0 && (
        <div className="action-buttons">
          {actions.map(action => (
            <button key={action.name} type="button" className={action === primary ? '' : 'secondary'}
                    onClick={() => (action.fields.length ? setActive(action.name) : runDirect(action))}>
              {action.label}
            </button>
          ))}
        </div>
      )}
      {errors.map(message => <p key={message} className="error" role="alert">{message}</p>)}
    </section>
  );
}
