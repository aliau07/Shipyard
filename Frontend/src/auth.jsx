import { createContext, useCallback, useContext, useEffect, useState } from 'react';
import { apiFetch, auth, logout as apiLogout } from './api';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [state, setState] = useState({ user: null, loading: Boolean(auth.getToken()) });

  useEffect(() => {
    if (!auth.getToken()) return undefined;
    let cancelled = false;
    apiFetch('/auth/me/')
      .then(user => { if (!cancelled) setState({ user, loading: false }); })
      .catch(() => { if (!cancelled) setState({ user: null, loading: false }); });
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    const handleLogout = () => setState({ user: null, loading: false });
    window.addEventListener('auth:logout', handleLogout);
    return () => window.removeEventListener('auth:logout', handleLogout);
  }, []);

  const signIn = useCallback(user => setState({ user, loading: false }), []);
  const updateUser = useCallback(user => setState(previous => ({ ...previous, user })), []);
  const signOut = useCallback(async () => {
    await apiLogout();
    setState({ user: null, loading: false });
  }, []);

  return (
    <AuthContext.Provider value={{ ...state, signIn, signOut, updateUser }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
