import React from 'react';
import { NavLink } from 'react-router-dom';
import { ADMIN_URL } from '../api';
import { useAuth } from '../auth';
import NotificationBell from './NotificationBell';

const NAV = [['/', 'Dashboard'], ['/projects', 'Projects'], ['/releases', 'Releases'], ['/releases/new', 'New release']];

export default function Layout({ children }) {
  const { user, signOut } = useAuth();
  return (
    <>
      <header className="topbar">
        <NavLink to="/" className="brand">Ship<span>yard</span></NavLink>
        <nav aria-label="Main">
          {NAV.map(([to, label]) => (
            <NavLink key={to} to={to} end={to === '/' || to === '/releases'}>{label}</NavLink>
          ))}
        </nav>
        <div className="topbar-user">
          <NotificationBell />
          <NavLink to="/profile" className="user-chip" title="Your profile">{user.display_name}</NavLink>
          {user.is_staff && <a href={ADMIN_URL}>Admin</a>}
          <button type="button" className="secondary small" onClick={signOut}>Log out</button>
        </div>
      </header>
      <main className="container">{children}</main>
    </>
  );
}
