import React, { useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { login } from '../api';
import { useAuth } from '../auth';
import { errorMessages } from '../format';

export default function Login() {
  const { signIn } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [errors, setErrors] = useState([]);
  const [saving, setSaving] = useState(false);

  async function submit(event) {
    event.preventDefault();
    setSaving(true);
    setErrors([]);
    try {
      const user = await login(username, password);
      signIn(user);
      const next = new URLSearchParams(location.search).get('next');
      navigate(next && next.startsWith('/') ? next : location.pathname, { replace: true });
    } catch (error) {
      setErrors(errorMessages(error));
      setSaving(false);
    }
  }

  return (
    <div className="auth-page">
      <div className="auth-card">
        <p className="brand-large">Ship<span>yard</span></p>
        <h2>Sign in</h2>
        <p className="muted">Plan releases in dependency order, collect sign-offs and ship in waves.</p>
        <form onSubmit={submit}>
          <label>Username or email<input value={username} onChange={e => setUsername(e.target.value)} autoComplete="username" required /></label>
          <label>Password<input type="password" value={password} onChange={e => setPassword(e.target.value)} autoComplete="current-password" required /></label>
          {errors.map(message => <p key={message} className="error" role="alert">{message}</p>)}
          <button type="submit" disabled={saving}>{saving ? 'Signing in...' : 'Sign in'}</button>
        </form>
        <p className="small">New here? <Link to="/signup">Create an account</Link></p>
      </div>
    </div>
  );
}
