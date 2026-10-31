# Shipyard

Shipyard is a release dependency planner for software teams. You describe the components you ship (services,
libraries and frontends), how they depend on each other, and which of them change in a release. Shipyard works out
the deploy order, groups components into waves that can go out in parallel, finds the critical path, shows what
else each change affects, and refuses to approve a release until every component owner has signed off and the
changed components don't depend on each other in a cycle.

The backend is a Django 5.2 + Django REST Framework API; the frontend is a React 18 single-page app.

## Features

- **Projects with roles.** Each member is an *owner* (manages people and the project), a *release manager* (runs
  releases, manages components) or an *engineer* (owns components, drafts and signs off releases). Anyone can sign
  up; owners add existing accounts by username or email. Non-members get `404` for everything in a project.
- **Components** of kind service, library or frontend, each with an owner, an estimated deploy time in minutes, an
  optional package name and repository link.
- **Dependencies** between components, added by hand or **imported from a manifest**: upload a `requirements.txt`
  (or any pip `.txt`/`.in` file) or a `package.json` for a component, and every package that matches another
  component becomes a dependency. Packages that match no component are listed back, and an import that closes a
  cycle says so.
- **Releases** containing component changes (feature, fix, breaking change, maintenance), with a workflow:

  | Action | From | Who | Notes |
  |---|---|---|---|
  | Submit for review | draft | any member (engineers: their own drafts) | needs at least one change |
  | Sign off | in review | owners of changed components; managers for unowned ones | signs off all of yours at once |
  | Approve release | in review | owner, release manager | every component signed off **and** no cycle |
  | Request changes | in review | owner, release manager | back to draft, sign-offs cleared |
  | Start rollout | approved | owner, release manager | |
  | Mark released | in progress | owner, release manager | |
  | Mark blocked | in review, approved, in progress | any member | reason required; remembers where it was |
  | Unblock | blocked | owner, release manager | returns to the status it was blocked from |
  | Cancel release | draft, in review, approved, blocked | owner, release manager | reason required |
  | Reopen | released, cancelled | owner, release manager | back to draft, sign-offs cleared |

  `workflow.py` is the single source of truth: the API returns `allowed_actions` for the signed-in user and the
  React app only shows those buttons; every action is re-checked on the server. Changes can only be edited while a
  release is a draft.
- **Release plan**: deploy waves (layered Kahn's algorithm), a full deploy order, the critical path (the longest
  chain of deploy minutes, the fastest the release can finish), the wave-by-wave estimate, and impact analysis
  listing every dependent of each changed component with the path that reaches it, including components that are
  not part of the release. Ordering follows dependencies through unchanged components too: if `web` reaches `api`
  only through an unchanged gateway, the new `web` still waits for the new `api`.
- **Graph view** in plain SVG, laid out by wave. Cycles are drawn in red with a dashed line and their components get
  their own "Blocked by cycle" column; selecting a component highlights its impact paths and lists them. Works with
  the keyboard (Tab, Enter).
- **Comments with screenshots** (up to five PNG/JPEG/WebP images per comment, re-encoded with Pillow so EXIF data
  is removed, with thumbnails), a **timeline** of every change, and **CSV export** of the release plan (wave, step,
  owner, timings, dependencies, critical path, sign-offs, affected components; protected against CSV injection).
- **Notifications** in the app (bell with unread count) and by email (console backend by default). Who hears about
  what depends on the event: submitting asks component owners and managers to sign off, sign-offs tell the author
  and managers, and so on. Nobody is told about their own action, and notifications are only sent after the
  database transaction commits.
- **Dashboard**: releases by status, blocked releases with reasons, upcoming target dates, the most depended-on
  components, and the average number of waves per release (releases whose components form a cycle are counted
  separately). Filter to one project with `?project=<id>`.

## The graph module

`Backend/apps/projects/graph.py` is pure Python with no Django imports. A graph is a dict mapping a component name
to the names it depends on. Every function breaks ties by name, so results are deterministic:

| Function | Returns |
|---|---|
| `find_cycle(graph)` | a cycle as a path such as `['orders', 'payments', 'orders']`, or `None` (iterative DFS, no recursion limit) |
| `topological_order(graph)` | dependencies first, ties by name; raises `CycleError` with the cycle path |
| `layers(graph)` / `waves(graph)` | layered Kahn's algorithm: `waves[0]` has no dependencies; `layers` also returns the nodes blocked by a cycle |
| `critical_path(graph, weights)` | `(total, path)`: the longest weighted chain in the DAG |
| `impact(graph, start)` | every dependent with its depth and shortest path from `start` (BFS) |
| `contract(graph, keep)` | the graph restricted to `keep`, keeping dependencies that run through removed nodes |

`Backend/apps/projects/manifests.py` is also pure Python. It handles comments, continuation lines, extras,
environment markers, hashes, `-r`/`-c`/`--index-url` options, editable installs with `#egg=`, direct references
(`name @ url`), local wheels and archives, byte order marks and Windows line endings in requirements files, and all
four dependency sections of `package.json`. Names are compared the way pip does (case-insensitive, `-`, `_` and `.`
equal), and a scoped npm package such as `@atlas/http-client` also matches a component called `http-client`.

## Project layout

```
Backend/
  config/            settings, URLs
  apps/core/         DomainError handler, image processing, pagination, health check, test helpers
  apps/accounts/     users, sign-up, token login
  apps/projects/     projects, memberships, components, dependencies, graph.py, manifests.py, scoping
  apps/releases/     releases, changes, sign-offs, workflow.py, planning, CSV export, comments and screenshots
  apps/notifications/ in-app and email notifications (listens to the release_event_recorded signal)
  apps/dashboard/    dashboard figures
  apps/demo/         seed_demo_data command
  schema.yml         OpenAPI 3 schema (generated)
Frontend/
  src/api.js, auth.jsx, hooks.js, format.js, graphLayout.js
  src/components/    GraphView, ActionPanel, Timeline, ManifestUpload, WavePlan, Layout, ...
  src/views/         Dashboard, Projects, ProjectDetail, ReleaseList, NewRelease, ReleaseDetail, ...
```

## Running it locally

Requirements: Python 3.11+, Node 18+.

```bash
# Backend
cd Backend
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                 # then set SECRET_KEY
python manage.py migrate
python manage.py seed_demo_data      # prints the demo accounts and their passwords
python manage.py runserver           # http://127.0.0.1:8000 (API docs at /)

# Frontend, in a second terminal
cd Frontend
npm ci
npm start                            # http://localhost:3000
```

Sign in as `raj` (release manager) to approve and run releases, as `li`, `ada` or `tomas` (engineers) to sign off
their components, or as `nora` (owner) to manage people. `admin` can use the Django admin at `/admin/`.

### Demo data

`seed_demo_data` creates the "Atlas Commerce" project: 12 components (libraries, Python services, an API gateway and
two React frontends) with 21 dependencies, four of them imported from a sample `requirements.txt` and
`package.json`. Its releases cover every stage:

- **Checkout revamp (2026.11.0)**: a valid plan in three waves, waiting for the last sign-off (auth-service).
- **Payment refund callbacks (2026.11.1)**: payments-service and orders-service now depend on each other, so the
  release is fully signed off but can't be approved until the cycle is broken.
- A released, a blocked, a cancelled and a draft release, plus comments with generated screenshots.

Passwords are generated on every run (set `DEMO_PASSWORD` to use one fixed password). Re-running leaves existing
data alone; `--reset` rebuilds the demo project.

## API

Token authentication: `POST /api/auth/token/` with a username (or email) and password returns a token; send it as
`Authorization: Token <token>`. Browsable docs are served at `/` (Swagger UI) and `/api/schema/redoc/`.

| Endpoint | |
|---|---|
| `/api/auth/register/`, `/api/auth/token/`, `/api/auth/logout/`, `/api/auth/me/` | accounts |
| `/api/projects/`, `/api/projects/{id}/graph/`, `/api/projects/{id}/members/[{membership_id}/]` | projects, graph, people |
| `/api/components/?project=`, `/api/components/{id}/manifest/`, `/api/components/{id}/impact/` | components, manifest import, impact |
| `/api/dependencies/?project=&component=` | dependencies |
| `/api/releases/?project=&status=`, `/api/releases/{id}/transition/` | releases and the workflow |
| `/api/releases/{id}/changes/[{change_id}/]`, `/api/releases/{id}/comments/`, `/api/releases/{id}/export/` | changes, comments (JSON or multipart with `images`), CSV |
| `/api/notifications/`, `/api/notifications/unread-count/`, `/api/notifications/read-all/` | notifications |
| `/api/dashboard/?project=` | dashboard |

Business-rule errors come back as `{"detail": "..."}` with `400`, `403` (your role can't do that) or `409` (not in
this state, or blocked by a rule such as a missing sign-off or a cycle). Deleting a component that a release still
uses answers `409`.

Regenerate the schema after API changes:

```bash
python manage.py spectacular --file schema.yml
python manage.py spectacular --validate --file schema.yml
```

## Tests

```bash
cd Backend && python manage.py test                    # graph, manifests, workflow, API, scoping, query counts
cd Frontend && CI=true npm test -- --watchAll=false     # graph view, action buttons, uploads, release page
```

The graph and manifest tests are plain `unittest` tests that need no database. API tests check that non-members get
`404`s, role rules give `403`s, and that list, detail, graph and dashboard endpoints use a fixed number of queries
however much data there is.

To run the backend tests against PostgreSQL, set `DATABASE_URL`, for example
`DATABASE_URL=postgres://shipyard:shipyard-password@localhost:5432/shipyard python manage.py test`.

## Configuration

Settings come from environment variables or `Backend/.env` (see `Backend/.env.example`): `SECRET_KEY`, `DEBUG`,
`ALLOWED_HOSTS`, `DATABASE_URL` (SQLite by default), `CORS_ALLOWED_ORIGINS`, `FRONTEND_URL` (used in email links),
email settings (console backend by default), `MEDIA_ROOT` and API throttle rates. The frontend reads
`REACT_APP_API_URL` (see `Frontend/.env.example`).

Limits: five screenshots per comment, 5 MB per image, 512 KB per manifest, deploy times from 1 to 1440 minutes.
