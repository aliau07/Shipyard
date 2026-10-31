import { errorMessages, formatDate, formatDateTime, formatMinutes, humanDuration, pathText, roleLabel } from '../format';

test('deploy minutes read as hours and minutes', () => {
  expect(formatMinutes(45)).toBe('45 min');
  expect(formatMinutes(60)).toBe('1 h');
  expect(formatMinutes(135)).toBe('2 h 15 min');
  expect(formatMinutes(null)).toBe('');
});

test('dates are DD/MM/YYYY and times 24-hour UTC', () => {
  expect(formatDate('2026-03-05')).toBe('05/03/2026');
  expect(formatDateTime('2026-10-08T13:30:00Z')).toBe('08/10/2026 13:30 UTC');
  expect(formatDateTime(null)).toBe('');
});

test('human durations', () => {
  expect(humanDuration(30 * 60000)).toBe('30 min');
  expect(humanDuration(3 * 3600000)).toBe('3 hours');
  expect(humanDuration(5 * 24 * 3600000)).toBe('5 days');
});

test('API error bodies become readable lines, including nested fields', () => {
  expect(errorMessages({ body: { detail: 'Nope.' } })).toEqual(['Nope.']);
  expect(errorMessages({ body: { version: ['This field is required.'], changes: [{ summary: ['Too long.'] }] } }))
    .toEqual(['version: This field is required.', 'changes: summary: Too long.']);
  expect(errorMessages({ message: 'Network down' })).toEqual(['Network down']);
});

test('paths and roles', () => {
  expect(pathText(['a', 'b', 'a'])).toBe('a → b → a');
  expect(roleLabel('release_manager')).toBe('Release manager');
  expect(roleLabel(undefined)).toBe('');
});
