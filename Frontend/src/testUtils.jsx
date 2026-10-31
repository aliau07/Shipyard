import { render } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { AuthProvider, useAuth } from './auth';

export function jsonResponse(body, status = 200, headers = {}) {
  return Promise.resolve({
    ok: status < 400,
    status,
    json: () => Promise.resolve(body),
    blob: () => Promise.resolve(new Blob([typeof body === 'string' ? body : JSON.stringify(body)])),
    headers: { get: name => headers[name] ?? null },
  });
}

export function mockApi(routes) {
  global.fetch = jest.fn((url, options = {}) => {
    const keys = Object.keys(routes).sort((a, b) => b.length - a.length);
    const match = keys.find(key => url.includes(key));
    if (!match) return jsonResponse({ count: 0, next: null, previous: null, results: [] });
    const value = routes[match];
    const body = typeof value === 'function' ? value(url, options) : value;
    return body && body.__status ? jsonResponse(body.body, body.__status) : jsonResponse(body);
  });
  return global.fetch;
}

export const ROUTER_FUTURE = { v7_startTransition: true, v7_relativeSplatPath: true };

function WhenSignedIn({ children }) {
  const { user } = useAuth();
  return user ? children : null;
}

export function renderWithProviders(ui, { path = '/', route = '*' } = {}) {
  return render(
    <MemoryRouter initialEntries={[path]} future={ROUTER_FUTURE}>
      <AuthProvider>
        <WhenSignedIn><Routes><Route path={route} element={ui} /></Routes></WhenSignedIn>
      </AuthProvider>
    </MemoryRouter>,
  );
}

export const MANAGER = { id: 2, username: 'raj', display_name: 'Raj Patel', first_name: 'Raj', email: 'raj@example.com', is_staff: false };
export const ENGINEER = { id: 3, username: 'li', display_name: 'Li Wei', first_name: 'Li', email: 'li@example.com', is_staff: false };

// The project graph from the backend tests: web -> api -> models, web -> ui, worker -> models.
export function sampleGraph(overrides = {}) {
  return {
    nodes: [
      { id: 1, name: 'models', kind: 'library', deploy_minutes: 5, owner_name: 'Li Wei', layer: 0, wave: 1, in_cycle: false },
      { id: 2, name: 'ui', kind: 'library', deploy_minutes: 4, owner_name: 'Ada Byrne', layer: 0, wave: 1, in_cycle: false },
      { id: 3, name: 'api', kind: 'service', deploy_minutes: 15, owner_name: 'Li Wei', layer: 1, wave: 2, in_cycle: false },
      { id: 4, name: 'worker', kind: 'service', deploy_minutes: 12, owner_name: null, layer: 1, wave: 2, in_cycle: false },
      { id: 5, name: 'web', kind: 'frontend', deploy_minutes: 8, owner_name: 'Ada Byrne', layer: 2, wave: 3, in_cycle: false },
    ],
    edges: [
      { from: 'api', to: 'models' }, { from: 'web', to: 'api' }, { from: 'web', to: 'ui' }, { from: 'worker', to: 'models' },
    ],
    layers: [['models', 'ui'], ['api', 'worker'], ['web']],
    waves: [['models', 'ui'], ['api', 'worker'], ['web']],
    blocked: [],
    cycle: null,
    order: ['models', 'api', 'ui', 'web', 'worker'],
    critical_path: { minutes: 28, path: ['models', 'api', 'web'] },
    estimated_minutes: 28,
    impact: {
      models: [
        { name: 'api', depth: 1, path: ['models', 'api'], in_view: true },
        { name: 'worker', depth: 1, path: ['models', 'worker'], in_view: true },
        { name: 'web', depth: 2, path: ['models', 'api', 'web'], in_view: true },
      ],
      ui: [{ name: 'web', depth: 1, path: ['ui', 'web'], in_view: true }],
      api: [{ name: 'web', depth: 1, path: ['api', 'web'], in_view: true }],
      worker: [],
      web: [],
    },
    ...overrides,
  };
}

export function cyclicGraph() {
  return sampleGraph({
    nodes: [
      { id: 2, name: 'ui', kind: 'library', deploy_minutes: 4, owner_name: null, layer: 0, wave: 1, in_cycle: false },
      { id: 3, name: 'api', kind: 'service', deploy_minutes: 15, owner_name: null, layer: 1, wave: null, in_cycle: true },
      { id: 1, name: 'models', kind: 'library', deploy_minutes: 5, owner_name: null, layer: 1, wave: null, in_cycle: true },
    ],
    edges: [{ from: 'api', to: 'models' }, { from: 'models', to: 'api' }],
    layers: [['ui'], ['api', 'models']],
    waves: null,
    blocked: ['api', 'models'],
    cycle: ['api', 'models', 'api'],
    order: null,
    critical_path: null,
    estimated_minutes: null,
    impact: { ui: [], api: [{ name: 'models', depth: 1, path: ['api', 'models'], in_view: true }], models: [] },
  });
}
