import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import App from '../App';
import { AuthProvider } from '../auth';
import { MANAGER, ROUTER_FUTURE, mockApi } from '../testUtils';

const DASHBOARD = {
  project: null,
  summary: { projects: 1, releases: 3, open: 2, in_review: 1, blocked: 1, released_recently: 1, recent_days: 30 },
  by_status: [{ key: 'draft', label: 'Draft', count: 1 }, { key: 'blocked', label: 'Blocked', count: 1 }],
  blocked_releases: [{ id: 5, reference: 'REL-0005', title: 'Inventory sync v2', version: '2026.11.2', status: 'blocked', status_display: 'Blocked', project: 1, project_name: 'Atlas Commerce', target_date: null, blocked_reason: 'Waiting for the migration window.', updated_at: '2026-10-30T10:00:00Z' }],
  upcoming_releases: [],
  most_depended_on: [{ id: 1, name: 'shared-models', kind: 'library', project: 1, project_name: 'Atlas Commerce', dependents: 5, owner_name: 'Li Wei' }],
  waves: { average: 2.5, releases: 2, with_cycles: 1 },
};

function renderApp(path = '/') {
  return render(
    <MemoryRouter initialEntries={[path]} future={ROUTER_FUTURE}>
      <AuthProvider><App /></AuthProvider>
    </MemoryRouter>,
  );
}

beforeEach(() => localStorage.clear());

test('signed-out visitors see the sign-in form and can sign in', async () => {
  const fetchMock = mockApi({ '/auth/token/': { token: 'abc', user: MANAGER }, '/dashboard/': DASHBOARD, '/notifications/unread-count/': { unread: 0 } });
  renderApp();

  fireEvent.change(screen.getByLabelText('Username or email'), { target: { value: 'raj' } });
  fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'secret-pass' } });
  fireEvent.click(screen.getByRole('button', { name: 'Sign in' }));

  expect(await screen.findByRole('heading', { name: 'Dashboard' })).toBeInTheDocument();
  expect(localStorage.getItem('shipyard.authToken')).toBe('abc');
  expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({ username: 'raj', password: 'secret-pass' });
});

test('the dashboard shows blocked releases, top components and average waves', async () => {
  localStorage.setItem('shipyard.authToken', 'tok');
  mockApi({ '/auth/me/': MANAGER, '/dashboard/': DASHBOARD, '/notifications/unread-count/': { unread: 3 } });
  renderApp();

  expect(await screen.findByText('Inventory sync v2')).toBeInTheDocument();
  expect(screen.getByText('Waiting for the migration window.')).toBeInTheDocument();
  expect(screen.getByText('shared-models (Atlas Commerce)')).toBeInTheDocument();
  expect(screen.getByText('2.5')).toBeInTheDocument();
  expect(screen.getByText('1 release has a dependency cycle.')).toBeInTheDocument();
  expect(screen.getByRole('navigation', { name: 'Main' })).toHaveTextContent('DashboardProjectsReleasesNew release');
  await waitFor(() => expect(screen.getByRole('link', { name: 'Notifications, 3 unread' })).toBeInTheDocument());
});

test('unknown pages say so', async () => {
  localStorage.setItem('shipyard.authToken', 'tok');
  mockApi({ '/auth/me/': MANAGER, '/notifications/unread-count/': { unread: 0 } });
  renderApp('/nowhere');

  expect(await screen.findByRole('heading', { name: 'Page not found' })).toBeInTheDocument();
});

test('an expired token signs the user out', async () => {
  localStorage.setItem('shipyard.authToken', 'old');
  mockApi({ '/auth/me/': { __status: 401, body: { detail: 'Invalid token.' } } });
  renderApp('/releases');

  expect(await screen.findByRole('button', { name: 'Sign in' })).toBeInTheDocument();
  expect(localStorage.getItem('shipyard.authToken')).toBeNull();
});
