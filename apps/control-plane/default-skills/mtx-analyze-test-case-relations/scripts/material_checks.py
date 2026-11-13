"""Canonical material schema and relationship checks; bundled into consumers."""
from jsonschema import Draft202012Validator


def validate_material(data, schema):
    errors = [f"{'/'.join(map(str, e.absolute_path)) or '/'}: {e.message}" for e in Draft202012Validator(schema).iter_errors(data)]
    if errors:
        return errors
    for key in ('sources', 'materialBlocks', 'functions', 'questions'):
        ids = [item['id'] for item in data[key]]
        if len(ids) != len(set(ids)):
            errors.append(f'{key}: duplicate id')
    sources = {s['id'] for s in data['sources']}
    blocks = {b['id']: b for b in data['materialBlocks']}
    for b in data['materialBlocks']:
        if b['kind'] == 'table':
            rows, covered = b['content']['rows'], set()
            for span in b['content'].get('spans', []):
                for row in range(span['row'], span['row'] + span['rowSpan']):
                    for col in range(span['column'], span['column'] + span['columnSpan']):
                        if row >= len(rows) or col >= len(rows[row]) or (row, col) in covered:
                            errors.append(f"{b['id']}: invalid or overlapping table span")
                        covered.add((row, col))
        if b['sourceId'] not in sources:
            errors.append(f"{b['id']}: missing source {b['sourceId']}")
        seen = {b['id']}
        parent = b['parentId']
        while parent is not None:
            if parent not in blocks:
                errors.append(f"{b['id']}: missing parent {parent}")
                break
            if parent in seen:
                errors.append(f"{b['id']}: cyclic parent")
                break
            seen.add(parent)
            parent = blocks[parent]['parentId']
    function_ids = {f['id'] for f in data['functions']}
    for f in data['functions']:
        titles = [section['title'] for section in f['sections']]
        if len(titles) != len(set(titles)):
            errors.append(f"{f['id']}: duplicate section title")
        for section in f['sections']:
            for item in section['items']:
                for ref in item['materialBlockIds']:
                    if ref not in blocks:
                        errors.append(f"{f['id']}: missing block {ref}")
    for q in data['questions']:
        for function_id in q['functionIds']:
            if function_id not in function_ids:
                errors.append(f"{q['id']}: missing function {function_id}")
        for ref in q['materialBlockIds']:
            if ref not in blocks:
                errors.append(f"{q['id']}: missing block {ref}")
    return errors

