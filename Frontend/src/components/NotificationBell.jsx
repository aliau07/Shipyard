import React, { useCallback, useState } from 'react';
import { NavLink, useLocation } from 'react-router-dom';
import { apiFetch } from '../api';
import { usePolling } from '../hooks';
import Icon from './Icon';

export default function NotificationBell() {
  const [unread, setUnread] = useState(0);
  const location = useLocation();
  const refresh = useCallback(() => {
    apiFetch('/notifications/unread-count/').then(data => setUnread(data.unread)).catch(() => {});
  }, [location.key]); // eslint-disable-line react-hooks/exhaustive-deps
  usePolling(refresh, 30000);

  return (
    <NavLink to="/notifications" className="bell" aria-label={`Notifications, ${unread} unread`}>
      <Icon name="bell" size={20} />
      {unread > 0 && <span className="bell-count">{unread > 99 ? '99+' : unread}</span>}
    </NavLink>
  );
}
