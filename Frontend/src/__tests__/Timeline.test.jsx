import { fireEvent, render, screen } from '@testing-library/react';
import { CommentForm, Timeline } from '../components/Timeline';
import { mockApi } from '../testUtils';

const ITEMS = [
  { type: 'event', id: 1, kind: 'blocked', kind_display: 'Blocked', actor_name: 'Raj Patel', message: 'Waiting for QA', from_status: 'approved', to_status: 'blocked', created_at: '2026-10-26T10:00:00Z' },
  { type: 'comment', id: 2, author_name: 'Ada Byrne', body: 'See the error page', created_at: '2026-10-26T11:00:00Z',
    screenshots: [{ id: 5, image: '/media/a.jpg', thumbnail: '/media/a-thumb.jpg' }] },
  { type: 'event', id: 3, kind: 'commented', kind_display: 'Comment', actor_name: 'Ada Byrne', message: 'See the error page', from_status: '', to_status: '', created_at: '2026-10-26T11:00:00Z' },
];

test('events show status changes and comments show their screenshots', () => {
  render(<Timeline items={ITEMS} />);

  expect(screen.getByText('Approved → Blocked')).toBeInTheDocument();
  expect(screen.getByText('Waiting for QA')).toBeInTheDocument();
  expect(screen.getAllByText('See the error page')).toHaveLength(1);
  expect(screen.getByRole('img', { name: 'Screenshot 1' })).toHaveAttribute('src', '/media/a-thumb.jpg');

  fireEvent.click(screen.getByRole('button', { name: 'Open screenshot 1' }));
  expect(screen.getByRole('dialog', { name: 'Screenshot' })).toBeInTheDocument();
});

test('only PNG, JPEG and WebP screenshots can be attached, five at most', () => {
  mockApi({});
  render(<CommentForm release={{ id: 7 }} onPosted={() => {}} />);
  const input = screen.getByLabelText('Attach screenshots');

  fireEvent.change(input, { target: { files: [new File(['x'], 'notes.pdf', { type: 'application/pdf' })] } });
  expect(screen.getByRole('alert')).toHaveTextContent('"notes.pdf" is not a PNG, JPEG or WebP image.');

  const many = [];
  for (let index = 0; index < 6; index += 1) many.push(new File(['x'], `shot${index}.png`, { type: 'image/png' }));
  fireEvent.change(input, { target: { files: many } });
  expect(screen.getByRole('alert')).toHaveTextContent('Attach up to 5 screenshots.');
  expect(screen.getAllByRole('button', { name: /^Remove shot/ })).toHaveLength(5);
});
