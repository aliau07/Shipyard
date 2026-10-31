"""CSV export of a release plan: one row per changed component, in deploy order."""
import csv
import io

from django.http import HttpResponse
from django.utils.text import slugify

from .planning import plan_for

COLUMNS = ['Wave', 'Step', 'Component', 'Kind', 'Owner', 'Deploy minutes', 'Change type', 'Summary',
           'Waits for', 'On critical path', 'Signed off by', 'Also affects']


def _safe(value):
    """Stop spreadsheet apps treating user text as a formula (CSV injection)."""
    text = str(value)
    return f"'{text}" if text[:1] in ('=', '+', '-', '@', '\t', '\r') else text


def plan_rows(release):
    """The plan as rows of strings, header first. Components on a cycle have no wave or step."""
    plan = plan_for(release)
    nodes = {}
    for node in plan['nodes']:
        nodes[node['name']] = node
    waits_for = {}
    for name in nodes:
        waits_for[name] = []
    for edge in plan['edges']:
        waits_for[edge['from']].append(edge['to'])
    signed_by = {}
    for sign_off in release.sign_offs.all():
        signed_by[sign_off.component.name] = sign_off.user.display_name if sign_off.user_id else ''
    kinds = {}
    for change in release.changes.all():
        kinds[change.component.name] = (change.component.get_kind_display(), change.get_change_type_display())
    critical = set(plan['critical_path']['path']) if plan['critical_path'] else set()

    if plan['order']:
        ordered = plan['order']
    else:
        ordered = []
        for layer in plan['layers']:
            ordered.extend(layer)

    rows = [COLUMNS]
    for step, name in enumerate(ordered, start=1):
        node = nodes[name]
        also = []
        for entry in plan['impact'][name]:
            if not entry['in_view']:
                also.append(entry['name'])
        rows.append([
            node['wave'] if node['wave'] is not None else 'cycle',
            step if plan['order'] else '',
            name, kinds[name][0], node['owner_name'] or '', node['deploy_minutes'], kinds[name][1], node['summary'],
            ', '.join(sorted(waits_for[name])), 'yes' if name in critical else 'no', signed_by.get(name, ''),
            ', '.join(also),
        ])
    return rows


def plan_csv(release):
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    for row in plan_rows(release):
        safe_row = []
        for value in row:
            safe_row.append(_safe(value))
        writer.writerow(safe_row)
    response = HttpResponse('' + buffer.getvalue(), content_type='text/csv; charset=utf-8')
    name = slugify(f'{release.project.name}-{release.version}') or 'release'
    response['Content-Disposition'] = f'attachment; filename="release-plan-{name}.csv"'
    return response
