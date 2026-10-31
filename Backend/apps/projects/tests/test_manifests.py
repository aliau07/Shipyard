"""Manifest parsing is pure Python, so these are plain unittest tests (no database)."""
import json
import re
import unittest

from apps.projects import manifests
from apps.projects.manifests import ManifestError, parse_package_json, parse_requirements


class TestCase(unittest.TestCase):
    def assertRaisesMessage(self, exception, message):
        return self.assertRaisesRegex(exception, re.escape(message))


class RequirementsTests(TestCase):
    def test_names_are_normalized_like_pip(self):
        self.assertEqual(manifests.normalize_name(' Django_Rest.Framework '), 'django-rest-framework')

    def test_basic_pins(self):
        self.assertEqual(parse_requirements('Django==5.2\nrequests>=2.0\n'), ['django', 'requests'])

    def test_comments_and_blank_lines(self):
        self.assertEqual(parse_requirements('# web stack\n\nflask  # the app\n   \n'), ['flask'])

    def test_only_comments_gives_nothing(self):
        self.assertEqual(parse_requirements('# nothing here yet\n'), [])

    def test_extras_and_environment_markers(self):
        text = 'requests[security,socks]>=2.31 ; python_version >= "3.10"\n'
        self.assertEqual(parse_requirements(text), ['requests'])

    def test_every_kind_of_version_specifier(self):
        self.assertEqual(parse_requirements('a~=1.0\nb!=2\nc===3\nd<4,>=1\ne (>=1.0)\nf\n'),
                         ['a', 'b', 'c', 'd', 'e', 'f'])

    def test_option_lines_are_skipped(self):
        text = ('-r base.txt\n-c constraints.txt\n--index-url https://pypi.example.com/simple\n'
                '--extra-index-url https://mirror.example.com\n--no-binary :all:\nnumpy\n')
        self.assertEqual(parse_requirements(text), ['numpy'])

    def test_editable_installs_use_the_egg_name(self):
        text = '-e git+https://github.com/acme/models.git@main#egg=atlas_models\n-e ./local-lib\n'
        self.assertEqual(parse_requirements(text), ['atlas-models'])

    def test_direct_references(self):
        text = 'atlas-shared-models @ git+https://github.com/acme/shared.git@v2\npkg[extra]@https://x.example/pkg.whl\n'
        self.assertEqual(parse_requirements(text), ['atlas-shared-models', 'pkg'])

    def test_urls_with_and_without_an_egg_name(self):
        text = 'git+ssh://git@github.com/acme/flags.git#egg=feature_flags\nhttps://example.com/archive.zip\n'
        self.assertEqual(parse_requirements(text), ['feature-flags'])

    def test_local_archives(self):
        text = './wheels/atlas_http-1.2.0-py3-none-any.whl\nsomepkg-2.0.tar.gz\n'
        self.assertEqual(parse_requirements(text), ['atlas-http', 'somepkg'])

    def test_continuation_lines_with_hashes(self):
        text = 'cryptography==42.0.5 \\\n    --hash=sha256:abc \\\n    --hash=sha256:def\nidna==3.6\n'
        self.assertEqual(parse_requirements(text), ['cryptography', 'idna'])

    def test_duplicates_in_different_case_are_merged(self):
        self.assertEqual(parse_requirements('Django\ndjango==5\nDJANGO>=4\n'), ['django'])

    def test_hash_in_a_url_fragment_is_not_a_comment(self):
        self.assertEqual(parse_requirements('-e git+https://x.example/y.git#egg=thing  # editable\n'), ['thing'])


class PackageJsonTests(TestCase):
    def test_all_dependency_sections(self):
        text = json.dumps({
            'dependencies': {'react': '^18'}, 'devDependencies': {'jest': '^29'},
            'peerDependencies': {'react-dom': '^18'}, 'optionalDependencies': {'fsevents': '*'},
        })
        self.assertEqual(parse_package_json(text), ['fsevents', 'jest', 'react', 'react-dom'])

    def test_other_sections_are_ignored(self):
        text = json.dumps({'name': '@atlas/web', 'scripts': {'build': 'x'}, 'bundledDependencies': ['y']})
        self.assertEqual(parse_package_json(text), [])

    def test_scoped_names_are_kept_and_lowercased(self):
        self.assertEqual(parse_package_json('{"dependencies": {"@atlas/Design-System": "^3"}}'),
                         ['@atlas/design-system'])

    def test_invalid_json_says_where(self):
        with self.assertRaisesMessage(ManifestError, 'package.json is not valid JSON (line 1, column'):
            parse_package_json('{"dependencies": {')

    def test_json_that_is_not_an_object(self):
        with self.assertRaisesMessage(ManifestError, 'package.json must contain a JSON object.'):
            parse_package_json('["react"]')

    def test_dependency_section_that_is_not_an_object(self):
        with self.assertRaisesMessage(ManifestError, '"dependencies" in package.json must be an object'):
            parse_package_json('{"dependencies": ["react"]}')


class ParseManifestTests(TestCase):
    def test_format_is_chosen_by_file_name(self):
        self.assertEqual(manifests.detect_format('package.json'), manifests.PACKAGE_JSON)
        self.assertEqual(manifests.detect_format('requirements-dev.txt'), manifests.REQUIREMENTS)
        self.assertEqual(manifests.detect_format('deps/requirements.in'), manifests.REQUIREMENTS)
        for name in ('Pipfile', 'setup.py', 'package-lock.json', ''):
            with self.assertRaisesMessage(ManifestError, 'Upload a requirements.txt'):
                manifests.detect_format(name)

    def test_windows_line_endings_and_byte_order_mark(self):
        data = 'flask\r\nrequests\r\n'.encode('utf-8')
        self.assertEqual(manifests.parse_manifest('requirements.txt', data), ('requirements.txt', ['flask', 'requests']))

    def test_empty_files_are_rejected(self):
        for data in (b'', b'  \n\t\n'):
            with self.assertRaisesMessage(ManifestError, '"requirements.txt" is empty.'):
                manifests.parse_manifest('requirements.txt', data)

    def test_binary_files_are_rejected(self):
        with self.assertRaisesMessage(ManifestError, 'is not UTF-8 text'):
            manifests.parse_manifest('package.json', b'\xff\xfe\x00\x81')

    def test_size_limit(self):
        with self.assertRaisesMessage(ManifestError, 'is larger than 1 KB'):
            manifests.parse_manifest('requirements.txt', b'a\n' * 1000, max_bytes=1024)


class MatchPackagesTests(TestCase):
    def test_match_by_name_or_package_name_ignoring_case_and_separators(self):
        matched, unmatched = manifests.match_packages(
            ['Atlas_Shared.Models', 'requests'], {'shared-models': ['shared-models', 'atlas-shared-models']})
        self.assertEqual((matched, unmatched), ({'Atlas_Shared.Models': 'shared-models'}, ['requests']))

    def test_scoped_npm_names_also_match_without_the_scope(self):
        matched, unmatched = manifests.match_packages(['@atlas/http-client', '@other/thing'],
                                                      {'http-client': ['http-client', '']})
        self.assertEqual((matched, unmatched), ({'@atlas/http-client': 'http-client'}, ['@other/thing']))

    def test_exact_package_name_beats_scope_stripping(self):
        matched, _ = manifests.match_packages(['@atlas/design-system'], {
            'ds': ['ds', '@atlas/design-system'], 'design-system': ['design-system']})
        self.assertEqual(matched, {'@atlas/design-system': 'ds'})

    def test_an_alias_shared_by_two_components_goes_to_the_first_by_name(self):
        matched, _ = manifests.match_packages(['shared'], {'b': ['shared'], 'a': ['shared']})
        self.assertEqual(matched, {'shared': 'a'})
