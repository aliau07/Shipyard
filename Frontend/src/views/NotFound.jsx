import React from 'react';
import { Link } from 'react-router-dom';

export default function NotFound() {
  return (
    <div className="narrow">
      <h2>Page not found</h2>
      <p>This page doesn't exist, or your account can't see it. If you followed a link, check it's complete.</p>
      <Link className="button" to="/">Go to your home page</Link>
    </div>
  );
}
