import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { apiPost } from '../api';
import LoadState from '../components/LoadState';
import { errorMessages, roleLabel } from '../format';
import { useApi } from '../hooks';

export default function Projects() {
  const navigate = useNavigate();
  const { data, loading, error } = useApi('/projects/?page_size=100');
  const [values, setValues] = useState({ name: '', description: '' });
  const [errors, setErrors] = useState([]);

  async function create(event) {
    event.preventDefault();
    setErrors([]);
    try {
      const project = await apiPost('/projects/', values);
      navigate(`/projects/${project.id}`);
    } catch (problem) {
      setErrors(errorMessages(problem));
    }
  }

  return (
    <div>
      <div className="page-header"><h2>Projects</h2></div>
      <LoadState loading={loading} error={error}>
        {data && data.results.length === 0 && <p className="muted">You're not in any projects yet. Start one below.</p>}
        <div className="cards">
          {(data?.results ?? []).map(project => (
            <Link key={project.id} className="card card-link" to={`/projects/${project.id}`}>
              <strong>{project.name}</strong>
              <span className="muted small">{roleLabel(project.viewer_role)}</span>
              <span>{project.component_count} components · {project.open_release_count} open releases</span>
              {project.description && <span className="muted small">{project.description}</span>}
            </Link>
          ))}
        </div>
      </LoadState>
      <form className="card form new-project" onSubmit={create}>
        <h3>Start a project</h3>
        <label>Name<input value={values.name} onChange={e => setValues({ ...values, name: e.target.value })} required /></label>
        <label>Description<textarea rows={2} value={values.description} onChange={e => setValues({ ...values, description: e.target.value })} /></label>
        {errors.map(message => <p key={message} className="error" role="alert">{message}</p>)}
        <div className="actions"><button type="submit">Create project</button></div>
      </form>
    </div>
  );
}
