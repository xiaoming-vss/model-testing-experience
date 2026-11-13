#!/usr/bin/env python3
"""Validate case-relation protocol 2.0; business semantics need separate review."""
import argparse
import json
import sys
from pathlib import Path


def require(ok, message):
    if not ok:
        raise ValueError(message)


def keys(obj, expected, label):
    require(isinstance(obj, dict) and set(obj) == set(expected.split()),
            label + ': incorrect fields')


def string(value, label):
    require(isinstance(value, str) and bool(value.strip()),
            label + ': expected nonempty string')


def indexed(items, field, label):
    require(isinstance(items, list), label + ': expected array')
    result = {}
    for item in items:
        require(isinstance(item, dict) and field in item, label + ': missing ' + field)
        identifier = item[field]
        string(identifier, label + '.' + field)
        require(identifier not in result, label + ': duplicate ' + identifier)
        result[identifier] = item
    return result


def validate_cases(cases):
    require(isinstance(cases, dict) and 'cases' in cases, 'expected cases object')
    source = indexed(cases['cases'], 'case_id', 'input cases')
    for cid, case in source.items():
        for field in ('case_module', 'case_title', 'case_type', 'priority'):
            require(field in case, cid + ': missing ' + field)
            string(case[field], cid + '.' + field)
        for field in ('precondition', 'test_steps', 'expected_results'):
            require(field in case and isinstance(case[field], list), cid + '.' + field + ': expected array')
            if field != 'precondition':
                require(bool(case[field]), cid + '.' + field + ': expected nonempty content')
            for value in case[field]:
                string(value, cid + '.' + field)
    return source


def validate_material_file(path):
    # Historical/structure-only use retains the standard-library-only dependency.
    try:
        from jsonschema import Draft202012Validator
        from material_checks import validate_material
    except ImportError as exc:
        raise ValueError('material validation requires jsonschema; validation not completed') from exc
    material = read_json(path)
    schema = read_json(Path(__file__).resolve().parent.parent / 'references/material.schema.json')
    Draft202012Validator.check_schema(schema)
    errors = validate_material(material, schema)
    require(not errors, 'material: ' + '; '.join(errors))


def validate(data, cases=None):
    keys(data, 'schema_version main_paths edges', 'root')
    require(data['schema_version'] == '2.0', 'unsupported schema_version')
    paths = indexed(data['main_paths'], 'path_id', 'main_paths')
    edges = indexed(data['edges'], 'edge_id', 'edges')
    source = None
    if cases is not None:
        source = validate_cases(cases)
    references, pairs, orders = set(), {}, set()
    for eid, edge in edges.items():
        keys(edge, 'edge_id from_case_id to_case_id relation_type order', eid)
        a, b = edge['from_case_id'], edge['to_case_id']
        string(a, eid + '.from_case_id')
        string(b, eid + '.to_case_id')
        require(a != b, eid + ': self-edge is not allowed')
        require(edge['relation_type'] in ('next', 'branch'), eid + ': invalid relation_type')
        require(type(edge['order']) is int and edge['order'] > 0,
                eid + ': order must be a positive integer')
        require((a, b) not in pairs, eid + ': duplicate directed pair')
        require((a, edge['order']) not in orders, eid + ': duplicate order for source')
        pairs[a, b] = edge
        orders.add((a, edge['order']))
        references.update((a, b))
    sequences = set()
    for pid, path in paths.items():
        keys(path, 'path_id case_ids', pid)
        sequence = path['case_ids']
        require(isinstance(sequence, list) and len(sequence) >= 2,
                pid + ': main path needs at least two case IDs')
        for cid in sequence:
            string(cid, pid + '.case_ids')
        require(len(set(sequence)) == len(sequence), pid + ': repeated case ID')
        require(tuple(sequence) not in sequences, pid + ': duplicate main path')
        sequences.add(tuple(sequence))
        references.update(sequence)
        for a, b in zip(sequence, sequence[1:]):
            require((a, b) in pairs and pairs[a, b]['relation_type'] == 'next',
                    pid + ': adjacent cases need a matching next edge: ' + a + ' -> ' + b)
    # Shared portions are legal; a whole repeated/contained spine is not.
    ordered_paths = [(pid, path['case_ids']) for pid, path in paths.items()]
    for short_id, short in ordered_paths:
        for long_id, long in ordered_paths:
            if len(short) >= len(long):
                continue
            require(not any(long[i:i + len(short)] == short
                            for i in range(len(long) - len(short) + 1)),
                    short_id + ': main path is a contiguous subpath of ' + long_id)
    if source is not None:
        require(references <= set(source),
                'unknown case IDs: ' + ', '.join(sorted(references - set(source))))
    return references


def strict_object(items):
    result = {}
    for key, value in items:
        require(key not in result, 'duplicate JSON key: ' + key)
        result[key] = value
    return result


def reject_constant(value):
    raise ValueError('invalid JSON constant: ' + value)


def read_json(path):
    with open(path, encoding='utf-8') as stream:
        return json.load(stream, object_pairs_hook=strict_object, parse_constant=reject_constant)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('relations')
    parser.add_argument('--cases', help='Full original cases JSON; validates content shape and references')
    parser.add_argument('--material', help='Readable requirement material 0.2 JSON; requires jsonschema')
    parser.add_argument('--mode', choices=('canvas', 'history'),
                        help='Explicit workflow; omit only for compatibility or structure-only checks')
    args = parser.parse_args()
    try:
        if args.mode == 'canvas':
            require(args.cases is not None and args.material is not None,
                    'canvas mode requires --cases and --material; do not silently switch to history')
        if args.mode == 'history':
            require(args.cases is not None, 'history mode requires --cases')
            require(args.material is None, 'history mode is cases-only; use canvas with material')
        if args.material is not None:
            require(args.cases is not None, '--material requires --cases')
            validate_material_file(args.material)
        data = read_json(args.relations)
        source = read_json(args.cases) if args.cases is not None else None
        validate(data, source)
    except (ValueError, TypeError, KeyError, OSError) as exc:
        print('INVALID: ' + str(exc), file=sys.stderr)
        return 1
    if source is None:
        print('VALID: structure checked; original case references NOT checked (supply --cases).')
    else:
        print('VALID: full case input shape, relation structure and original case references checked.')
        if args.material is not None:
            print('Material structure, IDs and references checked; version pairing NOT verified.')
        if args.mode is None:
            print('Workflow mode not specified; canvas input requirements NOT verified.')
    print('Business semantics require separate review.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
