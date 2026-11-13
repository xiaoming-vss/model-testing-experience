#!/usr/bin/env python3
"""Build finite state comparisons bound to stable record identities.

The caller supplies source-backed XPath and the reviewed transition relation.
This is an internal step plan, not a case or a new executor protocol.
"""
import argparse
import json
from pathlib import Path

from ui_variable_template import parse_tokens


def literal(value):
    if not isinstance(value, str):
        raise ValueError('XPath literal must be a string')
    if '{{' in value or '}}' in value:
        raise ValueError('Template-like literal needs a separately bound identity variable')
    if "'" not in value:
        return "'" + value + "'"
    if '"' not in value:
        return '"' + value + '"'
    return 'concat(' + ', "\'", '.join("'" + part + "'" for part in value.split("'")) + ')'


def variable(name):
    if not isinstance(name, str):
        raise ValueError('Variable name must be a string')
    expression = '{{' + name + '|xpath}}'
    tokens = parse_tokens(expression)
    if len(tokens) != 1 or tokens[0].name != name:
        raise ValueError('Use an exact named variable, not a function or expression')
    return expression


def identity_expression(identity):
    if not isinstance(identity, dict) or len(identity) != 1:
        raise ValueError('identity must be exactly {literal: value} or {variable: name}')
    if 'literal' in identity:
        if not identity['literal']:
            raise ValueError('Record identity cannot be empty')
        return literal(identity['literal'])
    if 'variable' in identity:
        return variable(identity['variable'])
    raise ValueError('Unknown identity representation')


def build(config):
    required = {'anchorXPath', 'rowXPath', 'identityColumn', 'stateColumn', 'records',
                'transitions', 'scope', 'requireProgress'}
    if not isinstance(config, dict) or set(config) - required - {'timeoutMs'} or required - set(config):
        raise ValueError('Missing or unknown configuration fields')
    for key in ('anchorXPath', 'rowXPath'):
        if not isinstance(config[key], str) or not config[key].startswith('/'):
            raise ValueError(f'{key} must be a source-backed absolute XPath')
    for key in ('identityColumn', 'stateColumn'):
        if type(config[key]) is not int or config[key] < 1:
            raise ValueError(f'{key} must be a positive column index')
    if config['identityColumn'] == config['stateColumn']:
        raise ValueError('Identity and state must refer to different columns')
    if config['scope'] not in ('all', 'selected') or type(config['requireProgress']) is not bool:
        raise ValueError('Declare scope all/selected and requireProgress true/false explicitly')
    timeout = config.get('timeoutMs', 5000)
    if type(timeout) is not int or timeout < 1:
        raise ValueError('timeoutMs must be a positive integer')
    records = config['records']
    if not isinstance(records, list) or not records:
        raise ValueError('A nonempty, finite reviewed identity list is required')
    matrix = config['transitions']
    if not isinstance(matrix, dict) or not matrix:
        raise ValueError('Provide the reviewed transition relation')
    for before, after in matrix.items():
        literal(before)
        if not isinstance(after, list) or not after or any(not isinstance(x, str) for x in after):
            raise ValueError('Each state needs an explicit nonempty list of allowed successors')
        for state in after:
            literal(state)
    identities, names = [], []
    for record in records:
        if not isinstance(record, dict) or set(record) != {'identity', 'beforeVariable'}:
            raise ValueError('Each record needs identity and beforeVariable only')
        identities.append(identity_expression(record['identity']))
        names.append(record['beforeVariable'])
        variable(record['beforeVariable'])
        if record['beforeVariable'] == 'baseUrl':
            raise ValueError('beforeVariable cannot overwrite reserved saveTo variable baseUrl')
    if len(set(identities)) != len(identities) or len(set(names)) != len(names):
        raise ValueError('Record identities and before variables must be unique')
    protected_names = {record['identity']['variable'] for record in records if 'variable' in record['identity']}
    for key in ('anchorXPath', 'rowXPath'):
        protected_names.update(token.name for token in parse_tokens(config[key]))
    if protected_names.intersection(names):
        raise ValueError('Capturing a state must not overwrite an identity or scope binding')

    common = {'keyword': 'assert_visible', 'locatorType': 'xpath',
              'operationValue': str(timeout), 'continueOnFailure': False, 'enabled': True}
    identity_guards = [f'string-length(normalize-space({identity}))>0' for identity in identities]
    identity_guards.extend(f'{left}!={right}' for index, left in enumerate(identities) for right in identities[index+1:])
    before_steps, constraints, progress = [], list(identity_guards), []
    total = f"count({config['rowXPath']})={len(records)}"
    if config['scope'] == 'all':
        constraints.append(total)
    for index, (record, identity) in enumerate(zip(records, identities), 1):
        row = f"({config['rowXPath']})[normalize-space(td[{config['identityColumn']}])={identity}]"
        state = f"({row})/td[{config['stateColumn']}]"
        unique = f'count({row})=1'
        initial_guard = ' and '.join([unique, *identity_guards]) + (' and ' + total if config['scope'] == 'all' else '')
        before_steps.append({**common, 'orderNo': index, 'stepName': f'Capture initial state for record {index}',
                             'locatorValue': f'{state}[{initial_guard}]',
                             'saveTo': [{'name': record['beforeVariable'], 'source': 'text'}]})
        old = 'normalize-space(' + variable(record['beforeVariable']) + ')'
        # State comparisons run inside the identity-selected row predicate.
        # This keeps the same atomic observation without repeating the full
        # absolute cell path for every allowed successor.
        current = f"normalize-space(td[{config['stateColumn']}])"
        alternatives = []
        for source, destinations in matrix.items():
            allowed = ' or '.join(current + '=' + literal(dest) for dest in destinations)
            alternatives.append('(' + old + '=' + literal(source) + ' and (' + allowed + '))')
        legal_row = row + '[count(td[' + str(config['stateColumn']) + '])=1 and (' + ' or '.join(alternatives) + ')]'
        constraints.extend([unique, 'count(' + legal_row + ')=1'])
        progress.append('count(' + row + '[' + old + '!=' + current + '])=1')
    if config['requireProgress']:
        constraints.append('(' + ' or '.join(progress) + ')')
    after_steps = [{**common, 'orderNo': 1, 'stepName': 'Compare current states with the same record identities',
                    'locatorValue': '(' + config['anchorXPath'] + ')[' + ' and '.join(constraints) + ']'}]
    return {'beforeSteps': before_steps, 'afterSteps': after_steps,
            'scope': 'Finite identity-bound observations only; no waiting, refreshing or conditional loop is generated.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('config', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.resolve() == args.config.resolve():
        parser.error('Output must not overwrite the configuration')
    try:
        plan = build(json.loads(args.config.read_text(encoding='utf-8')))
        args.output.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding='utf-8')
    except (ValueError, OSError) as error:
        parser.exit(2, f'State plan failed: {error}\n')


if __name__ == '__main__':
    main()
