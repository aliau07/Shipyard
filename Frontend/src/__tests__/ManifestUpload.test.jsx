import { fireEvent, render, screen } from '@testing-library/react';
import ManifestUpload from '../components/ManifestUpload';
import { mockApi } from '../testUtils';

const COMPONENTS = [{ id: 4, name: 'web' }, { id: 5, name: 'api' }];

function setup(response) {
  const fetchMock = mockApi({ '/components/4/manifest/': response });
  const onImported = jest.fn();
  render(<ManifestUpload components={COMPONENTS} onImported={onImported} />);
  return { fetchMock, onImported };
}

function choose(file) {
  fireEvent.change(screen.getByLabelText('Component'), { target: { value: '4' } });
  fireEvent.change(screen.getByLabelText('Manifest file'), { target: { files: [file] } });
}

const packageJson = () => new File(['{"dependencies": {}}'], 'package.json', { type: 'application/json' });

test('the file picker waits for a component', () => {
  setup({});
  expect(screen.getByLabelText('Manifest file')).toBeDisabled();
  fireEvent.change(screen.getByLabelText('Component'), { target: { value: '4' } });
  expect(screen.getByLabelText('Manifest file')).toBeEnabled();
});

test('a successful import lists new links and unmatched packages', async () => {
  const { fetchMock, onImported } = setup({
    format: 'package.json', packages: 3, created: ['worker'], existing: ['ui'], unmatched: ['react', 'jest'], cycle: null,
  });

  choose(packageJson());

  expect(await screen.findByText('worker')).toBeInTheDocument();
  expect(screen.getByText('ui')).toBeInTheDocument();
  expect(screen.getByText('react')).toHaveClass('tag');
  expect(screen.getByText('jest')).toHaveClass('tag');
  expect(fetchMock.mock.calls[0][1].body).toBeInstanceOf(FormData);
  expect(onImported).toHaveBeenCalled();
});

test('server errors about the file are shown', async () => {
  setup({ __status: 400, body: { detail: 'package.json is not valid JSON (line 1, column 18).' } });

  choose(packageJson());

  expect(await screen.findByRole('alert')).toHaveTextContent('package.json is not valid JSON (line 1, column 18).');
});

test('files that are not manifests are refused before uploading', () => {
  const { fetchMock } = setup({});

  choose(new File(['[packages]'], 'Pipfile', { type: 'text/plain' }));

  expect(screen.getByRole('alert')).toHaveTextContent('"Pipfile" isn\'t a requirements.txt or package.json file.');
  expect(fetchMock).not.toHaveBeenCalled();
});

test('an import that closes a cycle warns about it', async () => {
  setup({ format: 'requirements.txt', packages: 1, created: ['api'], existing: [], unmatched: [], cycle: ['web', 'api', 'web'] });

  choose(new File(['api\n'], 'requirements.txt', { type: 'text/plain' }));

  expect(await screen.findByRole('alert')).toHaveTextContent('This created a dependency cycle: web → api → web');
});
