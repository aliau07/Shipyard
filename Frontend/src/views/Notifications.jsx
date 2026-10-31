import React from 'react';
import { useNavigate } from 'react-router-dom';
import { apiPost } from '../api';
import LoadState from '../components/LoadState';
import Pagination from '../components/Pagination';
import { formatDateTime } from '../format';
import { usePaginatedList } from '../hooks';

export default function Notifications() {
  const navigate = useNavigate();
  const { rows, count, page, setPage, loading, error, reload } = usePaginatedList('/notifications/');

  async function open(notification) {
    if (!notification.is_read) await apiPost(`/notifications/${notification.id}/read/`).catch(() => {});
    navigate(`/releases/${notification.release}`);
  }

  async function readAll() {
    await apiPost('/notifications/read-all/');
    reload();
  }

  return (
    <div className="narrow">
      <div className="page-header">
        <h2>Notifications</h2>
        <button type="button" className="secondary" onClick={readAll} disabled={!rows.some(n => !n.is_read)}>Mark all read</button>
      </div>
      <LoadState loading={loading && rows.length === 0} error={error}>
        {rows.length === 0 ? <p className="muted">You're all caught up.</p> : (
          <ul className="notifications">
            {rows.map(notification => (
              <li key={notification.id}>
                <button type="button" className={`notification ${notification.is_read ? '' : 'unread'}`} onClick={() => open(notification)}>
                  <span>{notification.message}</span>
                  <span className="muted small">{notification.project_name}</span>
                  <span className="muted small">{formatDateTime(notification.created_at)}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
        <Pagination page={page} count={count} onChange={setPage} />
      </LoadState>
    </div>
  );
}
