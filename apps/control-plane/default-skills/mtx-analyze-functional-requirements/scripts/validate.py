#!/usr/bin/env python3
"""Validate the analysis structure and references against its material input."""
import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator
from material_checks import validate_material


def no_duplicates(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"), object_pairs_hook=no_duplicates)


def main():
    if len(sys.argv) != 3:
        print("usage: validate.py <analysis.json> <material.json>", file=sys.stderr)
        return 2
    try:
        analysis = read(sys.argv[1])
        material = read(sys.argv[2])
        schema = read(Path(__file__).resolve().parent.parent / "references/output.schema.json")
        errors = list(Draft202012Validator(schema).iter_errors(analysis))
        if errors:
            for error in sorted(errors, key=lambda e: str(list(e.absolute_path))):
                print(f"schema {list(error.absolute_path)}: {error.message}", file=sys.stderr)
            return 1
        material_schema = read(Path(__file__).resolve().parent.parent / "references/material.schema.json")
        material_errors = validate_material(material, material_schema)
        if material_errors:
            raise ValueError('material: ' + '\n'.join(material_errors))
        def collect(items, label):
            ids = [item['id'] for item in items]
            if len(ids) != len(set(ids)):
                raise ValueError(f"duplicate id in {label}")
            return set(ids)
        sets = {key: collect(analysis[key], key) for key in ('testObjects', 'impactAreas', 'risks', 'openQuestions')}
        blocks = collect(material['materialBlocks'], 'materialBlocks')
        questions = collect(material['questions'], 'questions')
        for group in ('testObjects', 'impactAreas', 'risks', 'openQuestions'):
            for item in analysis[group]:
                for field, valid in (('sourceBlockIds', blocks), ('sourceQuestionIds', questions), ('testObjectIds', sets['testObjects']), ('impactAreaIds', sets['impactAreas']), ('riskIds', sets['risks'])):
                    missing = set(item.get(field, [])) - valid
                    if missing:
                        raise ValueError(f"{group}/{item['id']}: invalid {field}: {sorted(missing)}")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"validation failed: {exc}", file=sys.stderr)
        return 1
    print('validation passed (structure and references only)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
