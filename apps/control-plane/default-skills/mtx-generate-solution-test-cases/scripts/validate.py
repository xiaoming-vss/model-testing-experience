#!/usr/bin/env python3
"""Validate generated cases, or explicitly supplied platform case types."""
import argparse
import json
import sys
from pathlib import Path

try:
    from jsonschema import Draft202012Validator
except ImportError:
    sys.exit('缺少依赖 jsonschema；未完成校验。')


def read(path):
    def no_duplicates(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f'重复 JSON 键: {key}')
            result[key] = value
        return result
    return json.loads(Path(path).read_text(encoding='utf-8'), object_pairs_hook=no_duplicates)


def validate(data, schema):
    errors = [f'{e.json_path}: {e.message}' for e in Draft202012Validator(schema).iter_errors(data)]
    if errors:
        return errors
    titles = set()
    for index, case in enumerate(data['cases'], 1):
        label = f'用例 {index}'
        identity = (case['case_module'].strip(), case['case_title'].strip())
        if identity in titles:
            errors.append(f'{label}: 同模块标题重复')
        titles.add(identity)
        if len(case['test_steps']) != len(case['expected_results']):
            errors.append(f'{label}: 步骤与预期数量不同')
        for field in ('precondition', 'test_steps', 'expected_results'):
            for number, value in enumerate(case[field], 1):
                prefix = f'{number}. '
                if not value.startswith(prefix) or not value[len(prefix):].strip():
                    errors.append(f'{label}.{field}[{number}]: 应从 1 连续编号并包含正文')
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output')
    parser.add_argument('--case-types', help='调用方明确提供的类型规范：非空、不重复的字符串数组 JSON')
    args = parser.parse_args()
    try:
        schema = read(Path(__file__).resolve().parent.parent / 'references/output.schema.json')
        if args.case_types:
            types = read(args.case_types)
            if (not isinstance(types, list) or not types
                    or any(not isinstance(v, str) or not v.strip() for v in types)
                    or len(types) != len(set(types))):
                raise ValueError('替代类型必须是非空、不重复的字符串数组')
            schema['$defs']['case']['properties']['case_type'] = {'enum': types}
        Draft202012Validator.check_schema(schema)
        errors = validate(read(args.output), schema)
        if errors:
            raise ValueError('\n'.join(errors))
    except (OSError, ValueError) as exc:
        print(f'校验失败: {exc}', file=sys.stderr)
        return 1
    print('用例结构、分类、编号及步骤预期对应校验通过；不代表依据、执行或覆盖通过。')
    return 0


if __name__ == '__main__':
    sys.exit(main())
