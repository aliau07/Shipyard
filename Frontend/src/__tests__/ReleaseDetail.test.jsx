import { fireEvent, screen, waitFor } from '@testing-library/react';
import ReleaseDetail from '../views/ReleaseDetail';
import { ENGINEER, MANAGER, cyclicGraph, mockApi, renderWithProviders, sampleGraph } from '../testUtils';

function release(overrides = {}) {
  const plan = sampleGraph({ unchanged_dependents: ['worker'] });
  return {
    id: 7, reference: 'REL-0007', project: 1, project_name: 'Atlas Commerce', title: 'Checkout revamp', version: '2026.11.0',
    status: 'in_review', status_display: 'In review', target_date: '2026-11-20', created_by_name: 'Raj Patel',
    change_count: 2, blocked_reason: '', blocked_from: '', description: 'One-page checkout.', reopen_count: 0,
    created_at: '2026-10-25T10:00:00Z', updated_at: '2026-10-26T10:00:00Z', submitted_at: '2026-10-26T10:00:00Z',
    approved_at: null, started_at: null, released_at: null, closed_at: null, viewer_role: 'engineer',
    changes: [
      { id: 1, component: 3, component_name: 'api', component_kind: 'service', owner: 3, owner_name: 'Li Wei', change_type: 'feature', change_type_display: 'Feature', summary: 'Sessions' },
      { id: 2, component: 5, component_name: 'web', component_kind: 'frontend', owner: 4, owner_name: 'Ada Byrne', change_type: 'breaking', change_type_display: 'Breaking change', summary: 'One page' },
    ],
    sign_offs: [{ id: 9, component: 5, component_name: 'web', user: 4, user_name: 'Ada Byrne', note: '' }],
    allowed_actions: [{ name: 'sign_off', label: 'Sign off', fields: ['note'] }, { name: 'block', label: 'Mark blocked', fields: ['reason'] }],
    approval: { blockers: ['Waiting for sign-off on api (Li Wei).'], waiting_for: [{ component: 'api', owner_name: 'Li Wei' }], cycle: null },
    plan,
    timeline: [
      { type: 'event', id: 1, kind: 'submitted', kind_display: 'Submitted for review', actor_name: 'Raj Patel', message: '', from_status: 'draft', to_status: 'in_review', created_at: '2026-10-26T10:00:00Z' },
    ],
    ...overrides,
  };
}

beforeEach(() => {
  localStorage.setItem('shipyard.authToken', 'tok');
});

const open = () => renderWithProviders(<ReleaseDetail />, { path: '/releases/7', route: '/releases/:id' });

test('shows the wave plan, sign-offs and only the allowed actions', async () => {
  mockApi({ '/auth/me/': ENGINEER, '/releases/7/': release() });
  open();

  expect(await screen.findByRole('button', { name: 'Sign off' })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Mark blocked' })).toHaveClass('secondary');
  expect(screen.queryByRole('button', { name: 'Approve release' })).not.toBeInTheDocument();
  expect(screen.getByText('Wave 1', { selector: '.wave-label' })).toBeInTheDocument();
  expect(screen.getByText('models → api → web (28 min)')).toBeInTheDocument();
  expect(screen.getByText('Waiting for sign-off on api (Li Wei).')).toBeInTheDocument();
  expect(screen.getByText('waiting')).toBeInTheDocument();
  expect(screen.getByText('Draft → In review')).toBeInTheDocument();
});

test('a release with a cycle explains there is no deploy order', async () => {
  const plan = { ...cyclicGraph(), unchanged_dependents: [] };
  mockApi({
    '/auth/me/': MANAGER,
    '/releases/7/': release({
      plan, viewer_role: 'release_manager',
      approval: { blockers: ['These components depend on each other in a cycle: api → models → api. Break the cycle before approving.'], waiting_for: [], cycle: plan.cycle },
      allowed_actions: [{ name: 'request_changes', label: 'Request changes', fields: ['reason'] }],
    }),
  });
  open();

  expect(await screen.findByText('No deploy order is possible.')).toBeInTheDocument();
  expect(screen.getByText('Blocked by cycle')).toBeInTheDocument();
  expect(screen.getByText(/Break the cycle before approving/)).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Approve release' })).not.toBeInTheDocument();
});

test('signing off posts the transition and reloads', async () => {
  let signed = false;
  const fetchMock = mockApi({
    '/auth/me/': ENGINEER,
    '/releases/7/transition/': () => { signed = true; return release(); },
    '/releases/7/': () => (signed ? release({ allowed_actions: [], sign_offs: [] }) : release()),
  });
  open();

  fireEvent.click(await screen.findByRole('button', { name: 'Sign off' }));
  fireEvent.change(screen.getByLabelText('Note (optional)'), { target: { value: 'Load tested' } });
  fireEvent.click(screen.getAllByRole('button', { name: 'Sign off' }).at(-1));

  expect(await screen.findByText('Nothing for you to do right now.')).toBeInTheDocument();
  const call = fetchMock.mock.calls.find(([url]) => url.endsWith('/releases/7/transition/'));
  expect(JSON.parse(call[1].body)).toEqual({ action: 'sign_off', note: 'Load tested' });
});

test('the plan can be exported as CSV', async () => {
  URL.createObjectURL = jest.fn(() => 'blob:plan');
  URL.revokeObjectURL = jest.fn();
  jest.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
  const fetchMock = mockApi({ '/auth/me/': ENGINEER, '/releases/7/export/': 'Wave,Step\n', '/releases/7/': release() });
  open();

  fireEvent.click(await screen.findByRole('button', { name: /Export plan/ }));

  await waitFor(() => expect(URL.createObjectURL).toHaveBeenCalled());
  expect(fetchMock.mock.calls.some(([url]) => url.endsWith('/releases/7/export/'))).toBe(true);
});

test('comments can carry screenshots', async () => {
  const fetchMock = mockApi({ '/auth/me/': ENGINEER, '/releases/7/comments/': { id: 1 }, '/releases/7/': release() });
  open();

  fireEvent.change(await screen.findByLabelText('Add a comment'), { target: { value: 'Error page after deploy' } });
  fireEvent.change(screen.getByLabelText('Attach screenshots'), {
    target: { files: [new File(['png'], 'error.png', { type: 'image/png' })] },
  });
  expect(screen.getByText('error.png')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Post comment' }));

  await waitFor(() => expect(fetchMock.mock.calls.some(([url]) => url.endsWith('/releases/7/comments/'))).toBe(true));
  const [, options] = fetchMock.mock.calls.find(([url]) => url.endsWith('/releases/7/comments/'));
  expect(options.body).toBeInstanceOf(FormData);
  expect(options.body.get('body')).toBe('Error page after deploy');
  expect(options.body.getAll('images')).toHaveLength(1);
});
