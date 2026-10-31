export const STATUS_LABELS = {
  draft: 'Draft',
  in_review: 'In review',
  approved: 'Approved',
  in_progress: 'In progress',
  released: 'Released',
  blocked: 'Blocked',
  cancelled: 'Cancelled',
};

export const OPEN_STATUSES = ['draft', 'in_review', 'approved', 'in_progress', 'blocked'];

export const ROLE_LABELS = { owner: 'Owner', release_manager: 'Release manager', engineer: 'Engineer' };
export const KIND_LABELS = { service: 'Service', library: 'Library', frontend: 'Frontend' };
export const CHANGE_TYPE_LABELS = { feature: 'Feature', fix: 'Fix', breaking: 'Breaking change', chore: 'Maintenance' };

const partsFormat = new Intl.DateTimeFormat('en-GB', {
  timeZone: 'UTC', day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit',
  weekday: 'short', hourCycle: 'h23',
});

function parts(iso) {
  const result = {};
  for (const part of partsFormat.formatToParts(new Date(iso))) result[part.type] = part.value;
  return result;
}

export function formatDate(value) {
  if (!value) return '';
  if (/^\d{4}-\d{2}-\d{2}$/.test(value)) {
    const [year, month, day] = value.split('-');
    return `${day}/${month}/${year}`;
  }
  const p = parts(value);
  return `${p.day}/${p.month}/${p.year}`;
}

export function formatTime(iso) {
  if (!iso) return '';
  const p = parts(iso);
  return `${p.hour}:${p.minute}`;
}

export const formatDateTime = iso => (iso ? `${formatDate(iso)} ${formatTime(iso)} UTC` : '');

export function formatMinutes(minutes) {
  if (minutes === null || minutes === undefined) return '';
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  if (hours === 0) return `${rest} min`;
  return rest === 0 ? `${hours} h` : `${hours} h ${rest} min`;
}

export function humanDuration(milliseconds) {
  const minutes = Math.round(Math.abs(milliseconds) / 60000);
  if (minutes < 60) return `${minutes} min`;
  const hours = Math.round(minutes / 60);
  if (hours < 48) return `${hours} hour${hours === 1 ? '' : 's'}`;
  const days = Math.round(hours / 24);
  return `${days} day${days === 1 ? '' : 's'}`;
}

export const pathText = path => (path ? path.join(' → ') : '');

export function errorMessages(error) {
  const body = error?.body;
  if (!body || typeof body !== 'object' || Object.keys(body).length === 0) {
    return [error?.message || 'Something went wrong.'];
  }
  const messages = [];
  for (const [field, value] of Object.entries(body)) {
    if (value && typeof value === 'object' && !Array.isArray(value)) {
      for (const nested of errorMessages({ body: value })) messages.push(`${field.replace(/_/g, ' ')}: ${nested}`);
      continue;
    }
    const prefix = field === 'detail' || field === 'non_field_errors' ? '' : `${field.replace(/_/g, ' ')}: `;
    for (const message of Array.isArray(value) ? value : [value]) {
      messages.push(typeof message === 'object' ? `${prefix}${errorMessages({ body: message }).join(' ')}` : `${prefix}${message}`);
    }
  }
  return messages;
}

export const roleLabel = role => ROLE_LABELS[role] ?? role ?? '';
