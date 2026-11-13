#!/usr/bin/env python3
"""Case-local semantic audit evidence. Checks provenance/completeness, not truth."""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
import re
from pathlib import Path
import yaml

FIELDS = {'keyword', 'locatorType', 'locatorValue', 'operationValue', 'comparator',
          'saveTo', 'missingFields', 'continueOnFailure', 'enabled'}
VERDICTS = {'supported', 'fillable_gap', 'design_dependency', 'unresolved'}

def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()

def ensure(condition, message):
    if not condition:
        raise ValueError(message)

def pairs(design, rows):
    cases = [c for c in design['cases'] if c['coverage'] != 'excluded']
    ensure([c['name'] for c in cases] == [r['name'] for r in rows], 'Candidate names/order changed')
    return list(zip(cases, rows))

def targets(case):
    result = []
    for step in case['steps']:
        for group, key in [('actions', 'actionId'), ('expectations', 'expectationId')]:
            for item in step.get(group, []):
                if item['status'] == 'included':
                    result.append({'id': item[key], 'kind': group, 'source': copy.deepcopy(item),
                                   'verdict': 'pending', 'clauses': [], 'reason': ''})
    ensure(len({t['id'] for t in result}) == len(result), 'Duplicate design target')
    return result

def initialize(design, rows):
    return {'designHash': digest(design), 'cases': [
        {'caseId': c['caseId'], 'candidateHash': digest(row), 'targets': targets(c)}
        for c, row in pairs(design, rows)]}

def aligned(design, rows, book, allow_changed=False):
    expected = initialize(design, rows)
    ensure(book['designHash'] == expected['designHash'], 'Design changed; start a fresh audit')
    ensure([c['caseId'] for c in book['cases']] == [c['caseId'] for c in expected['cases']], 'Audit case IDs changed')
    for wanted, actual in zip(expected['cases'], book['cases']):
        ensure([t['id'] for t in wanted['targets']] == [t['id'] for t in actual['targets']], 'Audit target IDs/order changed')
        for a, b in zip(wanted['targets'], actual['targets']):
            ensure(all(a[k] == b[k] for k in ('id', 'kind', 'source')), f"{a['id']}: source changed")
        if not allow_changed:
            ensure(wanted['candidateHash'] == actual['candidateHash'],
                   f"{actual['caseId']}: candidate changed; refresh and re-audit this case")
    return expected

def refresh(design, rows, book):
    expected = aligned(design, rows, book, allow_changed=True)
    result = copy.deepcopy(book)
    changed = []
    for index, (wanted, actual) in enumerate(zip(expected['cases'], result['cases'])):
        if wanted['candidateHash'] != actual['candidateHash']:
            result['cases'][index] = wanted
            changed.append(wanted['caseId'])
    return result, changed

def bind(design, rows, book, case_id):
    aligned(design, rows, book)
    result = copy.deepcopy(book)
    found = False
    for (_, row), case in zip(pairs(design, rows), result['cases']):
        if case['caseId'] != case_id:
            continue
        found = True
        steps = {s['orderNo']: s for s in row['stepsJson']}
        ensure(len(steps) == len(row['stepsJson']), 'Duplicate candidate orderNo')
        for target in case['targets']:
            for clause in target['clauses']:
                for ref in clause['refs']:
                    number, field = ref['orderNo'], ref['field']
                    ensure(type(number) is int and number in steps, 'Reference missing step')
                    ensure(field in FIELDS and field in steps[number], 'Reference actual executable field, not a step label')
                    ref['value'] = copy.deepcopy(steps[number][field])
                    ref['stepHash'] = digest(steps[number])
    ensure(found, 'Unknown caseId')
    return result

def check(design, rows, book):
    aligned(design, rows, book)
    counts = {v: 0 for v in sorted(VERDICTS)}
    unresolved = []
    for (_, row), case in zip(pairs(design, rows), book['cases']):
        steps = {s['orderNo']: s for s in row['stepsJson']}
        ensure(len(steps) == len(row['stepsJson']), 'Duplicate candidate orderNo')
        for target in case['targets']:
            identity = f"{case['caseId']}/{target['id']}"
            verdict = target['verdict']
            ensure(verdict in VERDICTS, f'{identity}: pending verdict')
            counts[verdict] += 1
            if verdict in {'unresolved', 'design_dependency'}:
                ensure(str(target.get('reason', '')).strip(), f'{identity}: explain the precise dependency or mismatch')
                unresolved.append(identity)
                continue
            ensure(row.get('enabled') is not False, f'{identity}: disabled case')
            ensure(target['clauses'], f'{identity}: inspect each original clause')
            depth = target.get('reviewDepth', 'detailed')
            ensure(depth in ('basic', 'detailed'), f'{identity}: invalid reviewDepth')
            if depth == 'basic':
                ensure(len(target['clauses']) == 1 and verdict == 'supported', f'{identity}: basic review needs one supported static claim')
                ensure(target['source'].get('operation') != 'observe', f'{identity}: observation requires detailed review')
                ensure(target['source'].get('assertion') in (None, 'visible', 'text_eq', 'text_contains', 'url_eq', 'url_contains'), f'{identity}: complex assertion needs detailed review')
            referenced_gap = False
            for clause in target['clauses']:
                for key in (('claim',) if depth == 'basic' else ('claim', 'object', 'valueSource', 'scope', 'timing')):
                    ensure(isinstance(clause.get(key), str) and clause[key].strip(), f'{identity}: missing {key}')
                if depth == 'detailed' and (target['kind'] == 'expectations' or target['source'].get('operation') == 'observe'):
                    for key in ('counterexample', 'rejection'):
                        ensure(isinstance(clause.get(key), str) and clause[key].strip(), f'{identity}: missing {key}')
                ensure(clause.get('refs'), f'{identity}: reference actual fields')
                for ref in clause['refs']:
                    number, field = ref['orderNo'], ref['field']
                    ensure(type(number) is int and number in steps, f'{identity}: missing step')
                    step = steps[number]
                    if depth == 'basic':
                        expression = str(step.get('locatorValue', ''))
                        ensure(not step.get('saveTo') and not step.get('missingFields')
                               and '{{' not in expression and '{{' not in str(step.get('operationValue', ''))
                               and not (step.get('locatorType') == 'xpath' and re.search(r'count\(|preceding|following|\s(?:or|and)\s', expression)),
                               f'{identity}: runtime, compound or gap evidence needs detailed review')
                    ensure(step.get('enabled') is not False, f'{identity}: disabled step')
                    ensure(field in FIELDS and field in step, f'{identity}: missing executable field')
                    ensure(ref.get('stepHash') == digest(step) and 'value' in ref and ref['value'] == step[field],
                           f'{identity}: unbound/stale field evidence; bind current case')
                    if field == 'missingFields' and step[field]:
                        referenced_gap = True
                    if step[field] is None:
                        ensure(verdict == 'fillable_gap', f'{identity}: null field cannot prove supported coverage')
            if verdict == 'fillable_gap':
                ensure(referenced_gap, f'{identity}: cite the actual missingFields contract')
    return {'verdictCounts': counts, 'unresolvedTargets': unresolved,
            'scope': 'Audit completeness and evidence provenance only; semantic truth still needs review.'}

def derived_account(design, rows, book):
    report = check(design, rows, book)
    if report['unresolvedTargets']:
        blocked = [{'caseId': c['caseId'], 'targetId': t['id'], 'verdict': t['verdict'], 'reason': t['reason']}
                   for c in book['cases'] for t in c['targets'] if t['verdict'] in ('unresolved', 'design_dependency')]
        prefix = 'DESIGN_CONFIRMATION_REQUIRED' if any(t['verdict'] == 'design_dependency' for t in blocked) else 'GENERATION_INCOMPLETE'
        raise ValueError(prefix + ': ' + json.dumps(blocked, ensure_ascii=False))
    account = {'cases': [{'caseId': c['caseId'], 'targets': [
        {'id': t['id'], 'steps': sorted({ref['orderNo'] for clause in t['clauses'] for ref in clause['refs']}),
         'evidence': '; '.join(clause['claim'] for clause in t['clauses'])}
        for t in c['targets']]} for c in book['cases']]}
    from check_design_coverage import check_coverage
    check_coverage(design, rows, account)
    return account


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('command', choices=['init', 'packet', 'bind', 'refresh', 'check', 'account'])
    p.add_argument('--design', type=Path, required=True)
    p.add_argument('--candidate', type=Path, required=True)
    p.add_argument('--audit', type=Path, required=True)
    p.add_argument('--case-id')
    p.add_argument('--account-output', type=Path)
    a = p.parse_args()
    try:
        design = json.loads(a.design.read_text()); rows = yaml.safe_load(a.candidate.read_text())
        if a.command == 'init':
            ensure(not a.audit.exists(), 'Audit exists; choose a fresh path')
            book = initialize(design, rows)
        else:
            book = json.loads(a.audit.read_text())
            if a.command == 'refresh':
                book, changed = refresh(design, rows, book)
                print(json.dumps({'resetCases': changed}, ensure_ascii=False))
            elif a.command == 'bind':
                book = bind(design, rows, book, a.case_id)
            elif a.command == 'account':
                account = derived_account(design, rows, book)
                ensure(a.account_output is not None, 'account requires --account-output')
                ensure(a.account_output.resolve() not in {a.design.resolve(), a.candidate.resolve(), a.audit.resolve()}, 'account output must not overwrite inputs')
                a.account_output.write_text(json.dumps(account, ensure_ascii=False, indent=2)+'\n')
                print('Coverage account derived from the current ready audit'); return
            elif a.command == 'packet':
                aligned(design, rows, book)
                index = next(i for i, c in enumerate(book['cases']) if c['caseId'] == a.case_id)
                case, row = pairs(design, rows)[index]
                print(json.dumps({'designCase': case, 'candidateCase': row, 'auditCase': book['cases'][index]}, ensure_ascii=False, indent=2))
                return
            else:
                print(json.dumps(check(design, rows, book), ensure_ascii=False, indent=2)); return
        a.audit.write_text(json.dumps(book, ensure_ascii=False, indent=2) + '\n')
    except (ValueError, KeyError, TypeError, StopIteration, yaml.YAMLError) as exc:
        p.exit(1, f'Audit incomplete: {exc}\n')

if __name__ == '__main__':
    main()
