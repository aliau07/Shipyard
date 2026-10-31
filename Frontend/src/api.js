export const API_URL = process.env.REACT_APP_API_URL || 'http://127.0.0.1:8000/api';
export const ADMIN_URL = `${API_URL.replace(/\/api\/?$/, '')}/admin/`;

const TOKEN_KEY = 'shipyard.authToken';

export const auth = {
  getToken: () => localStorage.getItem(TOKEN_KEY),
  setToken: token => localStorage.setItem(TOKEN_KEY, token),
  clearToken: () => localStorage.removeItem(TOKEN_KEY),
};

export class ApiError extends Error {
  constructor(status, body) {
    super(`Request failed with status ${status}`);
    this.status = status;
    this.body = body;
  }
}

async function request(path, options = {}) {
  const token = auth.getToken();
  const isForm = options.body instanceof FormData;
  const response = await fetch(`${API_URL}${path}`, {
    ...options,
    headers: {
      ...(isForm ? {} : { 'Content-Type': 'application/json' }),
      ...(token ? { Authorization: `Token ${token}` } : {}),
      ...options.headers,
    },
  });
  if (response.status === 401 && token) {
    auth.clearToken();
    window.dispatchEvent(new Event('auth:logout'));
  }
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new ApiError(response.status, body);
  }
  return response;
}

export async function apiFetch(path, options = {}) {
  const response = await request(path, options);
  return response.status === 204 ? null : response.json();
}

export const apiPost = (path, data) => apiFetch(path, { method: 'POST', body: data === undefined ? undefined : JSON.stringify(data) });
export const apiPatch = (path, data) => apiFetch(path, { method: 'PATCH', body: JSON.stringify(data) });
export const apiDelete = path => apiFetch(path, { method: 'DELETE' });

export const MANIFEST_NAMES = /(^|[\\/])(package\.json|[^\\/]+\.txt|[^\\/]+\.in)$/i;

export async function uploadManifest(componentId, file) {
  const form = new FormData();
  form.append('file', file);
  return apiFetch(`/components/${componentId}/manifest/`, { method: 'POST', body: form });
}

export async function postComment(releaseId, body, screenshots = []) {
  if (screenshots.length === 0) return apiPost(`/releases/${releaseId}/comments/`, { body });
  const form = new FormData();
  form.append('body', body);
  for (const file of screenshots) form.append('images', file);
  return apiFetch(`/releases/${releaseId}/comments/`, { method: 'POST', body: form });
}

export async function downloadFile(path, fallbackName = 'download') {
  const response = await request(path);
  const disposition = response.headers.get('Content-Disposition') || '';
  const match = disposition.match(/filename="?([^";]+)"?/);
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement('a');
  link.href = url;
  link.download = match ? match[1] : fallbackName;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

export async function fetchAll(path) {
  const separator = path.includes('?') ? '&' : '?';
  const data = await apiFetch(`${path}${separator}page_size=100`);
  return Array.isArray(data) ? data : data.results;
}

export async function login(username, password) {
  auth.clearToken();
  const data = await apiPost('/auth/token/', { username, password });
  auth.setToken(data.token);
  return data.user;
}

export async function signUp(details) {
  auth.clearToken();
  const data = await apiPost('/auth/register/', details);
  auth.setToken(data.token);
  return data.user;
}

export async function logout() {
  try {
    await apiPost('/auth/logout/');
  } catch {
  } finally {
    auth.clearToken();
  }
}
