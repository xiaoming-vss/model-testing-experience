#!/usr/bin/env python3
"""Export a checked platform YAML list without hand-written flow scalars.

This preserves data and validates existing evidence; it does not prove semantics.
"""
import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

import yaml


def scalar(value):
    text = json.dumps(value, ensure_ascii=False, allow_nan=False)
    # YAML treats these Unicode characters as line breaks even inside quotes.
    return text.replace('\u0085', r'\u0085').replace('\u2028', r'\u2028').replace('\u2029', r'\u2029')


def repeated_string_renderer(cases):
    """Use scalar-only aliases; parsed case objects and step order stay unchanged."""
    counts = Counter()
    def collect(value):
        if isinstance(value, str):
            counts[value] += 1
        elif isinstance(value, list):
            for item in value: collect(item)
        elif isinstance(value, dict):
            for item in value.values(): collect(item)
    collect(cases)
    anchors = {}
    def render(value):
        if isinstance(value, str):
            quoted = scalar(value)
            if len(quoted) >= 24 and counts[value] > 1:
                if value in anchors:
                    return '*' + anchors[value]
                name = 's' + str(len(anchors) + 1)
                # Use an anchor only when its complete-document cost is lower.
                if (counts[value] - 1) * (len(quoted) - len(name) - 1) > len(name) + 2:
                    anchors[value] = name
                    return '&' + name + ' ' + quoted
            return quoted
        if isinstance(value, list):
            return '[' + ', '.join(render(item) for item in value) + ']'
        if isinstance(value, dict):
            return '{' + ', '.join(scalar(key) + ': ' + render(item) for key, item in value.items()) + '}'
        return scalar(value)
    return render


def serialize_compact(cases):
    if not isinstance(cases, list):
        raise ValueError('candidate must be a YAML/JSON list')
    if not cases:
        return '[]\n'
    render = repeated_string_renderer(cases)
    # Share only repeated scalar execution attributes. Omit those fields from
    # each step body so YAML merge expansion never creates duplicate keys.
    profile_fields = ('keyword', 'locatorType', 'enabled', 'continueOnFailure')
    def profile(step):
        return {key: step[key] for key in profile_fields if key in step}
    profiles = Counter(json.dumps(profile(step), sort_keys=True) for case in cases
                       if isinstance(case, dict) and isinstance(case.get('stepsJson'), list)
                       for step in case['stepsJson'] if isinstance(step, dict))
    profile_anchors = {}
    lines = []
    fields = {'name', 'enabled', 'orderNo', 'stepsJson'}
    for case in cases:
        if not isinstance(case, dict) or set(case) != fields:
            raise ValueError('case must have exactly name, enabled, orderNo, stepsJson')
        if not isinstance(case['stepsJson'], list):
            raise ValueError('stepsJson must be a list')
        lines.extend(['- name: ' + render(case['name']),
                      '  enabled: ' + render(case['enabled']),
                      '  orderNo: ' + render(case['orderNo'])])
        if case['stepsJson']:
            lines.append('  stepsJson:')
            for step in case['stepsJson']:
                if not isinstance(step, dict):
                    raise ValueError('each step must be an object')
                # Flow objects quote all literal strings; aliases reuse only strings.
                shared = profile(step)
                key = json.dumps(shared, sort_keys=True)
                if shared and profiles[key] > 1 and len(scalar(shared)) > 32:
                    if key in profile_anchors:
                        reference = '*' + profile_anchors[key]
                    else:
                        name = 'd' + str(len(profile_anchors) + 1)
                        profile_anchors[key] = name
                        reference = '&' + name + ' ' + render(shared)
                    body = {key: value for key, value in step.items() if key not in shared}
                    suffix = ', ' + render(body)[1:-1] if body else ''
                    lines.append('    - {<<: ' + reference + suffix + '}')
                else:
                    lines.append('    - ' + render(step))
        else:
            lines.append('  stepsJson: []')
    text = '\n'.join(lines) + '\n'
    restored = yaml.safe_load(text)
    if json.dumps(restored, sort_keys=True, allow_nan=False) != json.dumps(cases, sort_keys=True, allow_nan=False):
        raise ValueError('serialization changed candidate data')
    return text


class ReadableDumper(yaml.SafeDumper):
    def ignore_aliases(self, data):
        return True

    def increase_indent(self, flow=False, indentless=False):
        return super().increase_indent(flow, False)

    def represent_mapping(self, tag, mapping, flow_style=None):
        node = super().represent_mapping(tag, mapping, flow_style)
        for key, _ in node.value:
            if isinstance(key, yaml.ScalarNode):
                key.style = None
        return node


def quoted_string(dumper, value):
    return dumper.represent_scalar('tag:yaml.org,2002:str', value, style='"')


ReadableDumper.add_representer(str, quoted_string)


def serialize(cases, compact=False):
    # Validate the same field boundary for both formats before serialization.
    if compact:
        return serialize_compact(cases)
    if not isinstance(cases, list):
        raise ValueError('candidate must be a YAML/JSON list')
    ordered = []
    for case in cases:
        if not isinstance(case, dict) or set(case) != {'name', 'enabled', 'orderNo', 'stepsJson'}:
            raise ValueError('case must have exactly name, enabled, orderNo, stepsJson')
        if not isinstance(case['stepsJson'], list) or any(not isinstance(step, dict) for step in case['stepsJson']):
            raise ValueError('stepsJson must contain objects')
        ordered.append({key: case[key] for key in ('name', 'enabled', 'orderNo', 'stepsJson')})
    text = yaml.dump(ordered, Dumper=ReadableDumper, allow_unicode=True,
                     sort_keys=False, default_flow_style=False, width=100)
    if json.dumps(yaml.safe_load(text), sort_keys=True, allow_nan=False) != json.dumps(cases, sort_keys=True, allow_nan=False):
        raise ValueError('serialization changed candidate data')
    return text


def load_candidate(text):
    # A valid JSON document must retain JSON string semantics. YAML normalizes
    # native NEL/LS/PS characters inside JSON double-quoted strings.
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return yaml.safe_load(text)


def checked_export(candidate, design, account=None, audit=None, output=None, external_variables=(), compact=False, execution_profile=None):
    if audit is None or output is None:
        raise ValueError('audit and output are required')
    candidate, design, audit, output = [Path(p).resolve() for p in (candidate, design, audit, output)]
    account = Path(account).resolve() if account is not None else None
    protected = {candidate, design, audit}
    if account is not None: protected.add(account)
    if execution_profile is not None: protected.add(Path(execution_profile).resolve())
    if output in protected:
        raise ValueError('output must not overwrite an input or evidence file')
    rows = load_candidate(candidate.read_text(encoding='utf-8'))
    text = serialize(rows, compact=compact)
    from execution_profile import load_profile, candidate_feature_errors
    profile = load_profile(execution_profile)
    design_data = json.loads(design.read_text(encoding='utf-8'))
    if execution_profile is not None and design_data.get('capabilities') is not None and design_data['capabilities'] != profile['capabilities']:
        raise ValueError('DESIGN_CONFIRMATION_REQUIRED: reviewed capabilities conflict with execution profile')
    scripts = Path(__file__).resolve().parent
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=output.parent,
                                         prefix='.export-', suffix='.yaml', delete=False) as handle:
            handle.write(text)
            temporary = Path(handle.name)
        with tempfile.TemporaryDirectory(prefix='ui-export-account-') as directory:
            derived = str(Path(directory) / 'account.json')
            checks = [
                ['validate_ui_case.py', str(temporary), '--allow-missing', '--design', str(design)],
                ['check_variable_flow.py', str(temporary), *[arg for name in external_variables for arg in ('--external-variable', name)]],
                ['coverage_workbench.py', 'account', '--design', str(design), '--candidate', str(temporary), '--audit', str(audit), '--account-output', derived],
            ]
            if account is not None:
                checks.append(['check_design_coverage.py', str(temporary), '--design', str(design), '--account', str(account)])
            for name, *arguments in checks:
                subprocess.run([sys.executable, str(scripts / name), *arguments], check=True)
                if name == 'validate_ui_case.py':
                    feature_errors = candidate_feature_errors(rows, profile)
                    if feature_errors:
                        raise ValueError('DESIGN_CONFIRMATION_REQUIRED: ' + '; '.join(feature_errors))
        os.replace(temporary, output)
        return {'path': str(output), 'sha256': hashlib.sha256(text.encode()).hexdigest(),
                'bytes': len(text.encode()), 'parsedDataUnchanged': True, 'declaredExternalVariables': list(external_variables),
                'executionProfile': profile['profileId'], 'serialization': 'compact' if compact else 'readable',
                'scope': 'Structure, ready audit and evidence freshness; not semantic certification'}
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('candidate', 'design', 'audit', 'output'):
        parser.add_argument('--' + name, required=True, type=Path)
    parser.add_argument('--account', type=Path, help='Optional legacy account; new workflows derive it from audit')
    parser.add_argument('--compact', action='store_true', help='Opt in to flow objects and YAML aliases')
    parser.add_argument('--execution-profile', type=Path)
    parser.add_argument('--external-variable', dest='external_variables', action='append', default=[])
    args = parser.parse_args()
    try:
        print(json.dumps(checked_export(**vars(args)), ensure_ascii=False))
    except (ValueError, OSError, yaml.YAMLError, subprocess.CalledProcessError) as error:
        parser.exit(2, f'Export failed: {error}\n')


if __name__ == '__main__':
    main()
