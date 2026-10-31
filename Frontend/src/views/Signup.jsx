import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { signUp } from '../api';
import { useAuth } from '../auth';
import { errorMessages } from '../format';

const FIELDS = [
  ['first_name', 'First name', 'text', 'given-name'], ['last_name', 'Last name', 'text', 'family-name'],
  ['username', 'Username', 'text', 'username'], ['email', 'Email', 'email', 'email'],
  ['password', 'Password', 'password', 'new-password'],
];

export default function Signup() {
  const { signIn } = useAuth();
  const navigate = useNavigate();
  const [values, setValues] = useState({});
  const [errors, setErrors] = useState([]);
  const [saving, setSaving] = useState(false);

  async function submit(event) {
    event.preventDefault();
    setSaving(true);
    setErrors([]);
    try {
      signIn(await signUp(values));
      navigate('/projects', { replace: true });
    } catch (error) {
      setErrors(errorMessages(error));
      setSaving(false);
    }
  }

  return (
    <div className="auth-page">
      <div className="auth-card">
        <p className="brand-large">Ship<span>yard</span></p>
        <h2>Create an account</h2>
        <p className="muted">Start a project, or ask a project owner to add you once you have an account.</p>
        <form onSubmit={submit}>
          {FIELDS.map(([name, label, type, autoComplete]) => (
            <label key={name}>{label}
              <input type={type} autoComplete={autoComplete} value={values[name] ?? ''} required={!name.endsWith('_name')}
                     onChange={e => setValues(previous => ({ ...previous, [name]: e.target.value }))} />
            </label>
          ))}
          {errors.map(message => <p key={message} className="error" role="alert">{message}</p>)}
          <button type="submit" disabled={saving}>{saving ? 'Creating...' : 'Create account'}</button>
        </form>
        <p className="small">Already have an account? <Link to="/">Sign in</Link></p>
      </div>
    </div>
  );
}
