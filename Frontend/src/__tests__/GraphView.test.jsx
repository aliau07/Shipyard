import { fireEvent, render, screen } from '@testing-library/react';
import GraphView from '../components/GraphView';
import { cyclicGraph, sampleGraph } from '../testUtils';

const x = testId => Number(screen.getByTestId(testId).querySelector('rect').getAttribute('x'));

test('components are laid out in wave columns', () => {
  render(<GraphView graph={sampleGraph()} />);

  expect(screen.getByText('Wave 1')).toBeInTheDocument();
  expect(screen.getByText('Wave 3')).toBeInTheDocument();
  expect(x('node-models')).toBe(x('node-ui'));
  expect(x('node-api')).toBeGreaterThan(x('node-models'));
  expect(x('node-web')).toBeGreaterThan(x('node-api'));
  expect(screen.getByRole('img', { name: /5 components in 3 columns/ })).toBeInTheDocument();
});

test('every dependency is drawn as an arrow from dependency to dependent', () => {
  const { container } = render(<GraphView graph={sampleGraph()} />);

  expect(container.querySelectorAll('path.edge')).toHaveLength(4);
  expect(screen.getByTestId('edge-models-api')).toHaveAttribute('marker-end', 'url(#arrow)');
});

test('selecting a component highlights and lists its impact paths', () => {
  render(<GraphView graph={sampleGraph()} />);

  fireEvent.click(screen.getByRole('button', { name: /^models, Library/ }));

  expect(screen.getByTestId('node-models')).toHaveClass('node-selected');
  expect(screen.getByTestId('node-web')).toHaveClass('node-impacted');
  expect(screen.getByTestId('node-ui')).not.toHaveClass('node-impacted');
  expect(screen.getByTestId('edge-models-api')).toHaveClass('edge-impact');
  expect(screen.getByTestId('edge-api-web')).toHaveClass('edge-impact');
  expect(screen.getByTestId('edge-ui-web')).not.toHaveClass('edge-impact');
  expect(screen.getByRole('heading', { name: 'Impact of models' })).toBeInTheDocument();
  expect(screen.getByText('models → api → web')).toBeInTheDocument();

  fireEvent.click(screen.getByTestId('node-models'));
  expect(screen.queryByRole('heading', { name: 'Impact of models' })).not.toBeInTheDocument();
});

test('nodes can be selected from the keyboard', () => {
  render(<GraphView graph={sampleGraph()} />);

  fireEvent.keyDown(screen.getByTestId('node-web'), { key: 'Enter' });

  expect(screen.getByTestId('node-web')).toHaveAttribute('aria-pressed', 'true');
  expect(screen.getByText('Nothing depends on web.')).toBeInTheDocument();
});

test('cycles are highlighted and their column is labelled', () => {
  render(<GraphView graph={cyclicGraph()} />);

  expect(screen.getByRole('alert')).toHaveTextContent('Cycle: api → models → api');
  expect(screen.getByText('Blocked by cycle')).toBeInTheDocument();
  expect(screen.getByTestId('edge-models-api')).toHaveClass('edge-cycle');
  expect(screen.getByTestId('edge-api-models')).toHaveClass('edge-cycle');
  expect(screen.getByTestId('node-api')).toHaveClass('node-cycle');
  expect(screen.getByTestId('node-ui')).not.toHaveClass('node-cycle');
  expect(screen.getByRole('button', { name: 'api, Service, on a dependency cycle' })).toBeInTheDocument();
});

test('an empty graph shows a message instead', () => {
  render(<GraphView graph={sampleGraph({ nodes: [], edges: [], layers: [] })} emptyText="Nothing planned." />);
  expect(screen.getByText('Nothing planned.')).toBeInTheDocument();
});
