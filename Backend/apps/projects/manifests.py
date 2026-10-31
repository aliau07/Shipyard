"""Read package names from dependency manifests: requirements.txt (pip) and package.json (npm).

Pure Python with no Django imports. `parse_manifest(filename, data)` returns (format, names) or raises
ManifestError with a message fit to show to the person who uploaded the file.
"""
import json
import re

REQUIREMENTS = 'requirements.txt'
PACKAGE_JSON = 'package.json'
PACKAGE_JSON_SECTIONS = ('dependencies', 'devDependencies', 'peerDependencies', 'optionalDependencies')

_NAME = re.compile(r'^([A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?)')
_DIRECT_REFERENCE = re.compile(r'^([A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?)\s*(?:\[[^\]]*\])?\s*@\s*\S')
_EGG = re.compile(r'[#&]egg=([A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?)')
_ARCHIVE = re.compile(r'\.(whl|tar\.gz|tgz|zip|tar\.bz2)$', re.IGNORECASE)
_ARCHIVE_NAME = re.compile(r'^([A-Za-z0-9](?:[A-Za-z0-9._]*[A-Za-z0-9])?)-\d')
_COMMENT = re.compile(r'(^|\s)#.*$')


class ManifestError(ValueError):
    pass


def normalize_name(name):
    """Compare package names the way pip does (PEP 503): ignore case, and treat runs of -, _ and . as one -."""
    return re.sub(r'[-_.]+', '-', name.strip()).lower()


def detect_format(filename):
    base = (filename or '').replace('\\', '/').rsplit('/', 1)[-1].lower()
    if base == 'package.json':
        return PACKAGE_JSON
    if base.endswith('.txt') or base.endswith('.in'):
        return REQUIREMENTS
    raise ManifestError('Upload a requirements.txt (or other pip requirements .txt file) or a package.json file.')


def _logical_lines(text):
    """Requirement lines with comments removed and backslash continuations joined."""
    joined = []
    pending = ''
    for raw in text.splitlines():
        stripped = raw.rstrip()
        if stripped.endswith('\\'):
            pending += stripped[:-1] + ' '
            continue
        joined.append(pending + raw)
        pending = ''
    if pending:
        joined.append(pending)
    lines = []
    for line in joined:
        line = _COMMENT.sub('', line).strip()
        if line:
            lines.append(line)
    return lines


def _requirement_name(line):
    """The package a single requirement line installs, or None for options and unnamed paths or URLs."""
    if line.startswith('-e ') or line.startswith('--editable'):
        match = _EGG.search(line)
        return match.group(1) if match else None
    if line.startswith('-'):
        return None
    match = _DIRECT_REFERENCE.match(line)
    if match:
        return match.group(1)
    target = line.split(';', 1)[0].strip().split()[0]
    if '://' in target or target.startswith(('.', '/', '~')) or '/' in target or '\\' in target:
        match = _EGG.search(line)
        if match:
            return match.group(1)
        if _ARCHIVE.search(target):
            match = _ARCHIVE_NAME.match(re.split(r'[\\/]', target)[-1])
            return match.group(1) if match else None
        return None
    if _ARCHIVE.search(target):
        match = _ARCHIVE_NAME.match(target)
        return match.group(1) if match else None
    match = _NAME.match(line)
    return match.group(1) if match else None


def parse_requirements(text):
    """Package names in a pip requirements file, normalized and sorted.

    Handles comments, blank lines, continuations, version specifiers, extras, environment markers, hashes,
    direct references (`name @ url`), editable installs with #egg=, archives, and skips options such as
    -r, -c and --index-url.
    """
    names = set()
    for line in _logical_lines(text):
        name = _requirement_name(line)
        if name:
            names.add(normalize_name(name))
    return sorted(names)


def parse_package_json(text):
    """Package names from the dependency sections of an npm package.json, sorted."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as error:
        raise ManifestError(f'package.json is not valid JSON (line {error.lineno}, column {error.colno}).')
    if not isinstance(data, dict):
        raise ManifestError('package.json must contain a JSON object.')
    names = set()
    for section in PACKAGE_JSON_SECTIONS:
        dependencies = data.get(section)
        if dependencies is None:
            continue
        if not isinstance(dependencies, dict):
            raise ManifestError(f'"{section}" in package.json must be an object of package names and versions.')
        for name in dependencies:
            if name.strip():
                names.add(name.strip().lower())
    return sorted(names)


def parse_manifest(filename, data, max_bytes=None):
    """Return (format, package names) for an uploaded manifest's name and raw bytes."""
    manifest_format = detect_format(filename)
    if max_bytes is not None and len(data) > max_bytes:
        raise ManifestError(f'"{filename}" is larger than {max_bytes // 1024} KB.')
    try:
        text = data.decode('utf-8-sig')
    except UnicodeDecodeError:
        raise ManifestError(f'"{filename}" is not UTF-8 text.')
    if not text.strip():
        raise ManifestError(f'"{filename}" is empty.')
    if manifest_format == PACKAGE_JSON:
        return manifest_format, parse_package_json(text)
    return manifest_format, parse_requirements(text)


def match_packages(packages, components):
    """Pair package names with components.

    `components` maps a component name to the package names it is published under. Matching ignores case and
    -/_/. differences, and a scoped npm name also matches without its scope (@atlas/http-client -> http-client).
    Returns ({package: component}, [unmatched packages]).
    """
    index = {}
    for component in sorted(components):
        for alias in components[component]:
            if alias:
                index.setdefault(normalize_name(alias), component)
    matched = {}
    unmatched = []
    for package in packages:
        key = normalize_name(package)
        component = index.get(key)
        if component is None and key.startswith('@') and '/' in key:
            component = index.get(key.split('/', 1)[1])
        if component is None:
            unmatched.append(package)
        else:
            matched[package] = component
    return matched, unmatched
