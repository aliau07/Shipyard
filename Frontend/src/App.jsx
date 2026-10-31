import React from 'react';
import { Navigate, Route, Routes, useLocation } from 'react-router-dom';
import { useAuth } from './auth';
import Layout from './components/Layout';
import Dashboard from './views/Dashboard';
import Login from './views/Login';
import NewRelease from './views/NewRelease';
import NotFound from './views/NotFound';
import Notifications from './views/Notifications';
import Profile from './views/Profile';
import ProjectDetail from './views/ProjectDetail';
import Projects from './views/Projects';
import ReleaseDetail from './views/ReleaseDetail';
import ReleaseList from './views/ReleaseList';
import Signup from './views/Signup';

function SignedOut() {
  const location = useLocation();
  const next = new URLSearchParams(location.search).get('next');
  return (
    <Routes>
      <Route path="/signup" element={<Signup />} />
      <Route path="*" element={<Login key={next ?? 'login'} />} />
    </Routes>
  );
}

export default function App() {
  const { user, loading } = useAuth();
  const location = useLocation();

  if (loading) return <p className="container muted">Loading...</p>;
  if (!user) return <SignedOut />;

  const next = new URLSearchParams(location.search).get('next');
  if (next && next.startsWith('/')) return <Navigate to={next} replace />;

  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/projects" element={<Projects />} />
        <Route path="/projects/:id" element={<ProjectDetail />} />
        <Route path="/releases" element={<ReleaseList />} />
        <Route path="/releases/new" element={<NewRelease />} />
        <Route path="/releases/:id" element={<ReleaseDetail />} />
        <Route path="/notifications" element={<Notifications />} />
        <Route path="/profile" element={<Profile />} />
        <Route path="*" element={<NotFound />} />
      </Routes>
    </Layout>
  );
}
