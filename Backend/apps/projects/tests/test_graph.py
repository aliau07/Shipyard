"""The graph module is pure Python, so these are plain unittest tests (no database)."""
from pathlib import Path
import re
import unittest

from apps.projects import graph


class TestCase(unittest.TestCase):
    def assertRaisesMessage(self, exception, message):
        return self.assertRaisesRegex(exception, re.escape(message))

# app needs auth and db-client, which both need core.
DIAMOND = {'app': ['auth', 'db-client'], 'auth': ['core'], 'db-client': ['core'], 'core': []}


class BuildGraphTests(TestCase):
    def test_sorts_and_removes_duplicate_edges(self):
        self.assertEqual(graph.build_graph(['b', 'a'], [('b', 'a'), ('b', 'a')]), {'a': [], 'b': ['a']})

    def test_rejects_edges_to_unknown_nodes(self):
        with self.assertRaisesMessage(ValueError, "Edge 'a' -> 'ghost' names an unknown node."):
            graph.build_graph(['a'], [('a', 'ghost')])

    def test_nodes_that_only_appear_as_dependencies_are_included(self):
        self.assertEqual(graph.topological_order({'web': ['api']}), ['api', 'web'])

    def test_dependents_of_reverses_the_graph(self):
        self.assertEqual(graph.dependents_of(DIAMOND),
                         {'app': [], 'auth': ['app'], 'core': ['auth', 'db-client'], 'db-client': ['app']})

    def test_module_has_no_django_imports(self):
        source = Path(graph.__file__).read_text()
        self.assertNotIn('import django', source)
        self.assertNotIn('from django', source)


class EmptyGraphTests(TestCase):
    def test_everything_works_on_an_empty_graph(self):
        self.assertIsNone(graph.find_cycle({}))
        self.assertEqual(graph.topological_order({}), [])
        self.assertEqual(graph.waves({}), [])
        self.assertEqual(graph.critical_path({}, {}), (0, []))
        self.assertEqual(graph.contract({}, []), {})


class CycleTests(TestCase):
    def test_no_cycle_in_a_diamond(self):
        self.assertIsNone(graph.find_cycle(DIAMOND))

    def test_two_node_cycle(self):
        self.assertEqual(graph.find_cycle({'a': ['b'], 'b': ['a']}), ['a', 'b', 'a'])

    def test_self_dependency_is_a_cycle(self):
        self.assertEqual(graph.find_cycle({'a': ['a']}), ['a', 'a'])

    def test_path_follows_dependency_edges_from_the_first_name(self):
        self.assertEqual(graph.find_cycle({'c': ['a'], 'a': ['b'], 'b': ['c']}), ['a', 'b', 'c', 'a'])

    def test_path_leaves_out_nodes_that_only_lead_into_the_cycle(self):
        self.assertEqual(graph.find_cycle({'app': ['x'], 'x': ['y'], 'y': ['x']}), ['x', 'y', 'x'])

    def test_first_cycle_by_name_is_reported_when_there_are_several(self):
        cycles = {'d': ['c'], 'c': ['d'], 'b': ['a'], 'a': ['b']}
        self.assertEqual(graph.find_cycle(cycles), ['a', 'b', 'a'])

    def test_answer_does_not_depend_on_input_order(self):
        first = {'b': ['c'], 'a': ['b'], 'c': ['a', 'b']}
        second = {'c': ['b', 'a'], 'b': ['c'], 'a': ['b']}
        self.assertEqual(graph.find_cycle(first), graph.find_cycle(second))

    def test_long_chains_do_not_hit_the_recursion_limit(self):
        chain = {}
        for index in range(5000):
            chain[f'n{index:05d}'] = [f'n{index + 1:05d}'] if index < 4999 else []
        self.assertIsNone(graph.find_cycle(chain))
        self.assertEqual(len(graph.topological_order(chain)), 5000)

        chain['n04999'] = ['n00000']
        cycle = graph.find_cycle(chain)
        self.assertEqual((cycle[0], cycle[-1], len(cycle)), ('n00000', 'n00000', 5001))

    def test_cycle_edges(self):
        self.assertEqual(graph.cycle_edges(['a', 'b', 'a']), [('a', 'b'), ('b', 'a')])
        self.assertEqual(graph.cycle_edges(None), [])


class TopologicalOrderTests(TestCase):
    def test_dependencies_come_first_with_ties_by_name(self):
        self.assertEqual(graph.topological_order(DIAMOND), ['core', 'auth', 'db-client', 'app'])

    def test_independent_nodes_are_alphabetical(self):
        self.assertEqual(graph.topological_order({'c': [], 'a': [], 'b': []}), ['a', 'b', 'c'])

    def test_a_node_that_becomes_ready_later_still_goes_first_by_name(self):
        self.assertEqual(graph.topological_order({'b': ['a'], 'a': [], 'c': []}), ['a', 'b', 'c'])

    def test_cycle_raises_with_the_path(self):
        with self.assertRaises(graph.CycleError) as raised:
            graph.topological_order({'a': ['b'], 'b': ['a'], 'c': []})
        self.assertEqual(raised.exception.cycle, ['a', 'b', 'a'])
        self.assertEqual(str(raised.exception), 'Dependency cycle: a -> b -> a')

    def test_every_node_follows_its_dependencies(self):
        bigger = {'web': ['api', 'ui'], 'api': ['models', 'auth'], 'auth': ['models'], 'ui': [], 'cli': ['api'],
                  'models': []}
        order = graph.topological_order(bigger)
        for node, dependencies in bigger.items():
            for dependency in dependencies:
                self.assertLess(order.index(dependency), order.index(node))


class WaveTests(TestCase):
    def test_diamond_has_three_waves(self):
        self.assertEqual(graph.waves(DIAMOND), [['core'], ['auth', 'db-client'], ['app']])

    def test_independent_nodes_share_the_first_wave(self):
        self.assertEqual(graph.waves({'b': [], 'a': []}), [['a', 'b']])

    def test_a_node_waits_for_its_slowest_dependency_chain(self):
        self.assertEqual(graph.waves({'app': ['core', 'lib'], 'lib': ['core'], 'core': []}),
                         [['core'], ['lib'], ['app']])

    def test_layers_report_nodes_blocked_by_a_cycle(self):
        waves, blocked = graph.layers({'a': ['b'], 'b': ['a'], 'c': ['a'], 'd': []})
        self.assertEqual((waves, blocked), ([['d']], ['a', 'b', 'c']))

    def test_waves_raise_on_a_cycle(self):
        with self.assertRaises(graph.CycleError) as raised:
            graph.waves({'x': ['y'], 'y': ['x']})
        self.assertEqual(raised.exception.cycle, ['x', 'y', 'x'])

    def test_waves_do_not_depend_on_input_order(self):
        first = {'web': ['api', 'ui'], 'api': ['models'], 'ui': [], 'models': []}
        second = {'models': [], 'ui': [], 'api': ['models'], 'web': ['ui', 'api']}
        self.assertEqual(graph.waves(first), graph.waves(second))
        self.assertEqual(graph.waves(first), [['models', 'ui'], ['api'], ['web']])


class CriticalPathTests(TestCase):
    def test_longest_weighted_chain(self):
        weights = {'core': 5, 'auth': 10, 'db-client': 3, 'app': 2}
        self.assertEqual(graph.critical_path(DIAMOND, weights), (17, ['core', 'auth', 'app']))

    def test_ties_go_to_names_that_sort_first(self):
        weights = {'x': 5, 'y': 5, 'app': 1}
        self.assertEqual(graph.critical_path({'app': ['x', 'y'], 'x': [], 'y': []}, weights), (6, ['x', 'app']))

    def test_a_single_slow_deploy_can_be_the_critical_path(self):
        weights = {'a': 1, 'b': 1, 'heavy': 10}
        self.assertEqual(graph.critical_path({'a': ['b'], 'b': [], 'heavy': []}, weights), (10, ['heavy']))

    def test_missing_weights_count_as_zero(self):
        self.assertEqual(graph.critical_path({'a': ['b']}, {'a': 3}), (3, ['b', 'a']))

    def test_negative_weights_are_rejected(self):
        with self.assertRaisesMessage(ValueError, "Weight of 'a' must not be negative."):
            graph.critical_path({'a': []}, {'a': -1})

    def test_cycle_raises(self):
        with self.assertRaises(graph.CycleError):
            graph.critical_path({'a': ['b'], 'b': ['a']}, {'a': 1, 'b': 1})


class ImpactTests(TestCase):
    def test_every_dependent_with_its_path(self):
        self.assertEqual(graph.impact(DIAMOND, 'core'), [
            {'node': 'auth', 'depth': 1, 'path': ['core', 'auth']},
            {'node': 'db-client', 'depth': 1, 'path': ['core', 'db-client']},
            {'node': 'app', 'depth': 2, 'path': ['core', 'auth', 'app']},
        ])

    def test_nothing_depends_on_the_top(self):
        self.assertEqual(graph.impact(DIAMOND, 'app'), [])

    def test_paths_are_shortest_even_when_a_longer_one_sorts_first(self):
        hits = graph.impact({'a': ['core'], 'z': ['a', 'core'], 'core': []}, 'core')
        self.assertEqual(hits[1], {'node': 'z', 'depth': 1, 'path': ['core', 'z']})

    def test_cycles_are_walked_once_and_the_start_is_never_reported(self):
        self.assertEqual(graph.impact({'a': ['b'], 'b': ['a'], 'c': ['b']}, 'a'), [
            {'node': 'b', 'depth': 1, 'path': ['a', 'b']},
            {'node': 'c', 'depth': 2, 'path': ['a', 'b', 'c']},
        ])

    def test_unknown_start_is_an_error(self):
        with self.assertRaisesMessage(ValueError, "Unknown node 'ghost'."):
            graph.impact(DIAMOND, 'ghost')


class ContractTests(TestCase):
    def test_indirect_dependencies_through_removed_nodes_are_kept(self):
        chain = {'web': ['gateway'], 'gateway': ['api'], 'api': []}
        self.assertEqual(graph.contract(chain, ['web', 'api']), {'api': [], 'web': ['api']})

    def test_search_stops_at_kept_nodes(self):
        chain = {'web': ['api'], 'api': ['models'], 'models': []}
        self.assertEqual(graph.contract(chain, ['web', 'api', 'models']), chain)

    def test_cycles_between_kept_nodes_survive(self):
        contracted = graph.contract({'a': ['x'], 'x': ['b'], 'b': ['a']}, ['a', 'b'])
        self.assertEqual(contracted, {'a': ['b'], 'b': ['a']})
        self.assertEqual(graph.find_cycle(contracted), ['a', 'b', 'a'])

    def test_loops_back_to_the_start_through_removed_nodes_are_ignored(self):
        self.assertEqual(graph.contract({'a': ['x'], 'x': ['a']}, ['a']), {'a': []})

    def test_kept_nodes_missing_from_the_graph_are_isolated(self):
        self.assertEqual(graph.contract({'a': []}, ['a', 'new']), {'a': [], 'new': []})
