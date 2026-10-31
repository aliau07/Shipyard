import React, { useState } from 'react';
import { apiPatch } from '../api';
import { useAuth } from '../auth';
import { errorMessages } from '../format';

export default function Profile() {
  const { user, updateUser } = useAuth();
  const [values, setValues] = useState({ first_name: user.first_name ?? '', last_name: user.last_name ?? '', email: user.email ?? '' });
  const [errors, setErrors] = useState([]);
  const [saved, setSaved] = useState(false);

  async function submit(event) {
    event.preventDefault();
    setErrors([]);
    setSaved(false);
    try {
      updateUser(await apiPatch('/auth/me/', values));
      setSaved(true);
    } catch (error) {
      setErrors(errorMessages(error));
    }
  }

  const set = field => event => setValues(previous => ({ ...previous, [field]: event.target.value }));
  return (
    <div className="narrow">
      <h2>Your profile</h2>
      <form className="card form" onSubmit={submit}>
        <p className="muted">Signed in as <strong>{user.username}</strong>.</p>
        <div className="form-row">
          <label>First name<input value={values.first_name} onChange={set('first_name')} /></label>
          <label>Last name<input value={values.last_name} onChange={set('last_name')} /></label>
        </div>
        <label>Email<input type="email" value={values.email} onChange={set('email')} required /></label>
        {errors.map(message => <p key={message} className="error" role="alert">{message}</p>)}
        {saved && <p className="flash" role="status">Profile saved.</p>}
        <div className="actions"><button type="submit">Save</button></div>
      </form>
    </div>
  );
}
