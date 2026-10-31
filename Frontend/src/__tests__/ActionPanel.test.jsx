import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import ActionPanel from '../components/ActionPanel';
import { mockApi } from '../testUtils';

function release(overrides = {}) {
  return {
    id: 7, status: 'in_review', blocked_reason: '', approval: { blockers: [], waiting_for: [], cycle: null },
    allowed_actions: [
      { name: 'approve', label: 'Approve release', fields: ['note'] },
      { name: 'request_changes', label: 'Request changes', fields: ['reason'] },
      { name: 'block', label: 'Mark blocked', fields: ['reason'] },
    ],
    ...overrides,
  };
}

test('only the actions the API allows become buttons, the first main one primary', () => {
  render(<ActionPanel release={release()} onChanged={() => {}} />);

  expect(screen.getByRole('button', { name: 'Approve release' })).not.toHaveClass('secondary');
  expect(screen.getByRole('button', { name: 'Request changes' })).toHaveClass('secondary');
  expect(screen.getByRole('button', { name: 'Mark blocked' })).toHaveClass('secondary');
  expect(screen.queryByRole('button', { name: 'Sign off' })).not.toBeInTheDocument();
});

test('an action with fields opens a form and posts them', async () => {
  const fetchMock = mockApi({ '/releases/7/transition/': { id: 7 } });
  const onChanged = jest.fn();
  render(<ActionPanel release={release()} onChanged={onChanged} />);

  fireEvent.click(screen.getByRole('button', { name: 'Mark blocked' }));
  expect(screen.getByLabelText('Reason')).toBeRequired();
  fireEvent.change(screen.getByLabelText('Reason'), { target: { value: 'Waiting for the DBA' } });
  fireEvent.click(screen.getAllByRole('button', { name: 'Mark blocked' }).at(-1));

  await waitFor(() => expect(onChanged).toHaveBeenCalled());
  const [, options] = fetchMock.mock.calls[0];
  expect(JSON.parse(options.body)).toEqual({ action: 'block', reason: 'Waiting for the DBA' });
});

test('actions without fields run straight away', async () => {
  const fetchMock = mockApi({ '/releases/7/transition/': { id: 7 } });
  const onChanged = jest.fn();
  render(<ActionPanel release={release({ status: 'approved', allowed_actions: [{ name: 'start', label: 'Start rollout', fields: [] }] })}
                      onChanged={onChanged} />);

  fireEvent.click(screen.getByRole('button', { name: 'Start rollout' }));

  await waitFor(() => expect(onChanged).toHaveBeenCalled());
  expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({ action: 'start' });
});

test('server-side rule errors are shown', async () => {
  mockApi({ '/releases/7/transition/': { __status: 409, body: { detail: 'Waiting for sign-off on api (Li Wei).' } } });
  render(<ActionPanel release={release()} onChanged={() => {}} />);

  fireEvent.click(screen.getByRole('button', { name: 'Approve release' }));
  fireEvent.click(screen.getAllByRole('button', { name: 'Approve release' }).at(-1));

  expect(await screen.findByRole('alert')).toHaveTextContent('Waiting for sign-off on api (Li Wei).');
});

test('approval blockers explain why approve is missing', () => {
  render(<ActionPanel release={release({
    approval: { blockers: ['These components depend on each other in a cycle: a → b → a.'], waiting_for: [], cycle: ['a', 'b', 'a'] },
    allowed_actions: [{ name: 'block', label: 'Mark blocked', fields: ['reason'] }],
  })} onChanged={() => {}} />);

  expect(screen.getByText("Can't approve yet")).toBeInTheDocument();
  expect(screen.getByText(/cycle: a → b → a/)).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Approve release' })).not.toBeInTheDocument();
});
