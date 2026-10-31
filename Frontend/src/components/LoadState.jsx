import React from 'react';
import { errorMessages } from '../format';

export default function LoadState({ loading, error, children }) {
  if (error) {
    return <p className="error" role="alert">{errorMessages(error).join(' ')}</p>;
  }
  if (loading) {
    return <p className="muted">Loading...</p>;
  }
  return children;
}
