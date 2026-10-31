import React from 'react';
import { STATUS_META } from '../status';
import Icon from './Icon';

export default function StatusTag({ status }) {
  const { label, group, icon } = STATUS_META[status] ?? { label: status, group: 'neutral', icon: 'info' };
  return (
    <span className={`status-tag group-${group}`}>
      <Icon name={icon} size={14} />
      {label}
    </span>
  );
}
