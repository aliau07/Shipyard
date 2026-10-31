import React, { useCallback, useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { apiDelete, apiFetch, apiPost, fetchAll } from '../api';
import GraphView from '../components/GraphView';
import LoadState from '../components/LoadState';
import ManifestUpload from '../components/ManifestUpload';
import { KIND_LABELS, ROLE_LABELS, errorMessages, formatMinutes, pathText, roleLabel } from '../format';

function useProject(id) {
  const [state, setState] = useState({ project: null, graph: null, components: [], dependencies: [], loading: true, error: null });
  const load = useCallback(async () => {
    try {
      const [project, graph, components, dependencies] = await Promise.all([
        apiFetch(`/projects/${id}/`), apiFetch(`/projects/${id}/graph/`),
        fetchAll(`/components/?project=${id}`), apiFetch(`/dependencies/?project=${id}`),
      ]);
      setState({ project, graph, components, dependencies, loading: false, error: null });
    } catch (error) {
      setState(previous => ({ ...previous, loading: false, error }));
    }
  }, [id]);
  useEffect(() => { load(); }, [load]);
  return { ...state, reload: load };
}

function AddComponent({ project, onAdded }) {
  const empty = { name: '', kind: 'service', owner: '', deploy_minutes: 10, package_name: '' };
  const [values, setValues] = useState(empty);
  const [errors, setErrors] = useState([]);
  const set = field => event => setValues(previous => ({ ...previous, [field]: event.target.value }));

  async function submit(event) {
    event.preventDefault();
    setErrors([]);
    try {
      await apiPost('/components/', { ...values, project: project.id, owner: values.owner || null });
      setValues(empty);
      onAdded();
    } catch (error) {
      setErrors(errorMessages(error));
    }
  }

  return (
    <form className="card form" onSubmit={submit}>
      <h3>Add a component</h3>
      <div className="form-row">
        <label>Name<input value={values.name} onChange={set('name')} placeholder="orders-service" required /></label>
        <label>Kind
          <select value={values.kind} onChange={set('kind')}>
            {Object.entries(KIND_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select>
        </label>
      </div>
      <div className="form-row three">
        <label>Owner
          <select value={values.owner} onChange={set('owner')}>
            <option value="">No owner</option>
            {project.members.map(member => <option key={member.user.id} value={member.user.id}>{member.user.display_name}</option>)}
          </select>
        </label>
        <label>Deploy minutes<input type="number" min="1" max="1440" value={values.deploy_minutes} onChange={set('deploy_minutes')} required /></label>
        <label>Package name<input value={values.package_name} onChange={set('package_name')} placeholder="optional" /></label>
      </div>
      {errors.map(message => <p key={message} className="error" role="alert">{message}</p>)}
      <div className="actions"><button type="submit">Add component</button></div>
    </form>
  );
}

function AddDependency({ components, onAdded }) {
  const [values, setValues] = useState({ component: '', depends_on: '' });
  const [errors, setErrors] = useState([]);
  const [cycle, setCycle] = useState(null);

  async function submit(event) {
    event.preventDefault();
    setErrors([]);
    setCycle(null);
    try {
      const created = await apiPost('/dependencies/', { component: Number(values.component), depends_on: Number(values.depends_on) });
      setCycle(created.cycle);
      onAdded();
    } catch (error) {
      setErrors(errorMessages(error));
    }
  }

  const options = components.map(component => <option key={component.id} value={component.id}>{component.name}</option>);
  return (
    <form className="card form" onSubmit={submit}>
      <h3>Add a dependency</h3>
      <div className="form-row">
        <label>Component<select value={values.component} onChange={e => setValues({ ...values, component: e.target.value })} required>
          <option value="">Choose</option>{options}</select></label>
        <label>depends on<select value={values.depends_on} onChange={e => setValues({ ...values, depends_on: e.target.value })} required>
          <option value="">Choose</option>{options}</select></label>
      </div>
      {errors.map(message => <p key={message} className="error" role="alert">{message}</p>)}
      {cycle && <p className="error" role="alert">Added, but this closes a cycle: {pathText(cycle)}</p>}
      <div className="actions"><button type="submit" className="secondary">Add dependency</button></div>
    </form>
  );
}

function Members({ project, onChanged }) {
  const [values, setValues] = useState({ user: '', role: 'engineer' });
  const [errors, setErrors] = useState([]);
  const owner = project.viewer_role === 'owner';

  async function add(event) {
    event.preventDefault();
    setErrors([]);
    try {
      await apiPost(`/projects/${project.id}/members/`, values);
      setValues({ user: '', role: 'engineer' });
      onChanged();
    } catch (error) {
      setErrors(errorMessages(error));
    }
  }

  async function remove(member) {
    setErrors([]);
    try {
      await apiDelete(`/projects/${project.id}/members/${member.id}/`);
      onChanged();
    } catch (error) {
      setErrors(errorMessages(error));
    }
  }

  return (
    <section className="card">
      <h3>People</h3>
      <ul className="mini-list">
        {project.members.map(member => (
          <li key={member.id}>
            <span>{member.user.display_name}</span>
            <span className="muted small">{roleLabel(member.role)}</span>
            {owner && <button type="button" className="link danger-text push" onClick={() => remove(member)}>Remove</button>}
          </li>
        ))}
      </ul>
      {owner && (
        <form className="inline-form" onSubmit={add}>
          <input aria-label="Username or email" placeholder="Username or email" value={values.user}
                 onChange={e => setValues({ ...values, user: e.target.value })} required />
          <select aria-label="Role" value={values.role} onChange={e => setValues({ ...values, role: e.target.value })}>
            {Object.entries(ROLE_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select>
          <button type="submit" className="secondary small">Add</button>
        </form>
      )}
      {errors.map(message => <p key={message} className="error" role="alert">{message}</p>)}
    </section>
  );
}

export default function ProjectDetail() {
  const { id } = useParams();
  const { project, graph, components, dependencies, loading, error, reload } = useProject(id);
  const [errors, setErrors] = useState([]);

  async function removeDependency(dependency) {
    setErrors([]);
    try {
      await apiDelete(`/dependencies/${dependency.id}/`);
      reload();
    } catch (problem) {
      setErrors(errorMessages(problem));
    }
  }

  return (
    <LoadState loading={loading} error={error}>
      {project && (
        <div>
          <div className="page-header">
            <div>
              <h2>{project.name}</h2>
              <p className="muted">{project.description} {project.viewer_role && `· You are ${roleLabel(project.viewer_role).toLowerCase()}`}</p>
            </div>
            <Link className="button" to={`/releases/new?project=${project.id}`}>New release</Link>
          </div>
          <section className="card">
            <h3>Dependency graph</h3>
            <GraphView graph={graph} title={`${project.name} dependency graph`} />
          </section>
          <div className="detail-grid">
            <div>
              <section className="card">
                <h3>Components</h3>
                <div className="table-wrap">
                  <table className="dense">
                    <thead><tr><th>Name</th><th>Kind</th><th>Owner</th><th>Deploy</th><th>Needs</th><th>Used by</th></tr></thead>
                    <tbody>
                      {components.map(component => (
                        <tr key={component.id}>
                          <td><strong>{component.name}</strong>{component.package_name && <div className="muted small">{component.package_name}</div>}</td>
                          <td>{component.kind_display}</td>
                          <td>{component.owner_name ?? <span className="muted">none</span>}</td>
                          <td>{formatMinutes(component.deploy_minutes)}</td>
                          <td>{component.dependency_count}</td>
                          <td>{component.dependent_count}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>
              <section className="card">
                <h3>Dependencies</h3>
                {dependencies.length === 0 ? <p className="muted">No dependencies yet.</p> : (
                  <ul className="mini-list">
                    {dependencies.map(dependency => (
                      <li key={dependency.id}>
                        <span>{dependency.component_name} → {dependency.depends_on_name}</span>
                        <span className="muted small">{dependency.source_display}</span>
                        <button type="button" className="link danger-text push" onClick={() => removeDependency(dependency)}
                                aria-label={`Remove ${dependency.component_name} depends on ${dependency.depends_on_name}`}>Remove</button>
                      </li>
                    ))}
                  </ul>
                )}
                {errors.map(message => <p key={message} className="error" role="alert">{message}</p>)}
              </section>
            </div>
            <div>
              <Members project={project} onChanged={reload} />
              <ManifestUpload components={components} onImported={reload} />
              <AddDependency components={components} onAdded={reload} />
              {project.can_manage && <AddComponent project={project} onAdded={reload} />}
            </div>
          </div>
        </div>
      )}
    </LoadState>
  );
}
