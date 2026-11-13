#!/usr/bin/env python3
"""Check named-template availability within each case, without inventing inputs."""
import argparse
import json
from pathlib import Path

from ui_variable_template import parse_tokens


def check(cases, external_variables=()):
    if not isinstance(cases, list) or any(not isinstance(c, dict) or not isinstance(c.get('stepsJson'), list) for c in cases):
        raise ValueError('Candidate must contain case objects with stepsJson lists')
    declared = set(external_variables)
    for name in declared:
        tokens = parse_tokens('{{' + name + '}}')
        if len(tokens) != 1 or tokens[0].name != name:
            raise ValueError('External variables must be exact named bindings')
    issues = []
    for case_index, case in enumerate(cases, 1):
        if case.get('enabled', True) is False:
            continue
        available = {'baseUrl', *declared}
        for step_index, step in enumerate(case['stepsJson'], 1):
            if step.get('enabled', True) is False:
                continue
            # The executor renders the current step before applying saveTo.
            for field in ('locatorValue', 'operationValue'):
                value = step.get(field)
                if not isinstance(value, str):
                    continue
                for name in sorted({token.name for token in parse_tokens(value)}):
                    if name not in available:
                        issues.append({'caseIndex': case_index, 'stepIndex': step_index,
                                       'orderNo': step.get('orderNo'), 'field': field,
                                       'name': name, 'code': 'unavailable_variable'})
            if step.get('continueOnFailure', False) is False:
                available.update(rule['name'] for rule in step.get('saveTo', []))
    return {'issues': issues, 'declaredExternalVariables': sorted(declared),
            'scope': 'Within-case availability after declared gaps are filled; external binding provenance, capture identity and freshness still need semantic review.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('candidate', type=Path)
    parser.add_argument('--external-variable', action='append', default=[])
    args = parser.parse_args()
    try:
        from export_ui_case import load_candidate
        report = check(load_candidate(args.candidate.read_text(encoding='utf-8')), args.external_variable)
        print(json.dumps(report, ensure_ascii=False))
        if report['issues']:
            parser.exit(2, 'Named variables need a supplied binding or an earlier successful producer.\n')
    except (ValueError, KeyError, TypeError, OSError) as error:
        parser.exit(2, f'Variable-flow check failed: {error}\n')


if __name__ == '__main__':
    main()
