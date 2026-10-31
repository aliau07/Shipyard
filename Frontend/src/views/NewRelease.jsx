import React, { useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { apiPost, fetchAll } from '../api';
import { CHANGE_TYPE_LABELS, errorMessages } from '../format';
import { useApi } from '../hooks';

export default function NewRelease() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const projects = useApi('/projects/?page_size=100');
  const [values, setValues] = useState({ project: params.get('project') ?? '', title: '', version: '', target_date: '', description: '' });
  const [components, setComponents] = useState([]);
  const [changes, setChanges] = useState({});
  const [errors, setErrors] = useState([]);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setChanges({});
    if (!values.project) { setComponents([]); return; }
    fetchAll(`/components/?project=${values.project}`).then(setComponents).catch(() => setComponents([]));
  }, [values.project]);

  const set = field => event => setValues(previous => ({ ...previous, [field]: event.target.value }));
  const toggle = component => setChanges(previous => {
    const next = { ...previous };
    if (next[component.id]) delete next[component.id];
    else next[component.id] = { summary: '', change_type: 'feature' };
    return next;
  });
  const setChange = (id, field, value) => setChanges(previous => ({ ...previous, [id]: { ...previous[id], [field]: value } }));

  async function submit(event) {
    event.preventDefault();
    setSaving(true);
    setErrors([]);
    const payload = { ...values, project: Number(values.project), target_date: values.target_date || null, changes: [] };
    for (const [id, change] of Object.entries(changes)) payload.changes.push({ component: Number(id), ...change });
    try {
      const release = await apiPost('/releases/', payload);
      navigate(`/releases/${release.id}`);
    } catch (error) {
      setErrors(errorMessages(error));
      setSaving(false);
    }
  }

  return (
    <div className="narrow">
      <h2>New release</h2>
      <form className="card form" onSubmit={submit}>
        <label>Project
          <select value={values.project} onChange={set('project')} required>
            <option value="">Choose a project</option>
            {(projects.data?.results ?? []).map(project => <option key={project.id} value={project.id}>{project.name}</option>)}
          </select>
        </label>
        <div className="form-row three">
          <label>Title<input value={values.title} onChange={set('title')} required /></label>
          <label>Version<input value={values.version} onChange={set('version')} placeholder="2026.11.0" required /></label>
          <label>Target date<input type="date" value={values.target_date} onChange={set('target_date')} /></label>
        </div>
        <label>Description<textarea rows={2} value={values.description} onChange={set('description')} /></label>
        {components.length > 0 && (
          <fieldset>
            <legend>Changed components</legend>
            {components.map(component => (
              <div key={component.id} className="change-pick">
                <label className="check">
                  <input type="checkbox" checked={Boolean(changes[component.id])} onChange={() => toggle(component)} />
                  {component.name} <span className="muted small">{component.kind_display}</span>
                </label>
                {changes[component.id] && (
                  <div className="form-row">
                    <label>What changes in {component.name}?
                      <input value={changes[component.id].summary} required onChange={e => setChange(component.id, 'summary', e.target.value)} />
                    </label>
                    <label>Type
                      <select value={changes[component.id].change_type} onChange={e => setChange(component.id, 'change_type', e.target.value)}>
                        {Object.entries(CHANGE_TYPE_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
                      </select>
                    </label>
                  </div>
                )}
              </div>
            ))}
          </fieldset>
        )}
        {errors.map(message => <p key={message} className="error" role="alert">{message}</p>)}
        <div className="actions"><button type="submit" disabled={saving}>{saving ? 'Creating...' : 'Create draft'}</button></div>
      </form>
    </div>
  );
}
