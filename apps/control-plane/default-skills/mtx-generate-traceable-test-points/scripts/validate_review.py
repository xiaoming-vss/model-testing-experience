#!/usr/bin/env python3
"""Validate a single review batch; basis batches contain at most ten points."""
import sys

import jsonschema
from validate import read, validate_artifacts
from review_checks import TARGETS, validate_issues


def main():
    if len(sys.argv) not in (6, 7):
        print('用法: validate_review.py <材料.json> <范围分析.json> <候选.json> <审查.json> <basis|coverage|gaps> [批次ID.json]', file=sys.stderr)
        return 2
    try:
        material, scope, candidate, review = (read(path) for path in sys.argv[1:5])
        phase = sys.argv[5]
        if phase not in TARGETS or (phase == 'basis') != (len(sys.argv) == 7):
            raise ValueError('审查阶段无效，或批次 ID 参数与阶段不匹配')
        errors = validate_artifacts(material, scope, candidate)
        if errors:
            raise ValueError('输入候选无效：' + '\n'.join(errors))
        if not isinstance(review, dict) or set(review) != {'issues'}:
            raise ValueError('审查结果必须只包含 issues 数组')
        batch = read(sys.argv[6]) if phase == 'basis' else None
        errors = validate_issues(review['issues'], material, scope, candidate, phase, batch)
        if errors:
            raise ValueError('\n'.join(errors))
    except (OSError, ValueError, KeyError, TypeError, jsonschema.ValidationError, jsonschema.SchemaError) as exc:
        print(f'审查校验失败: {exc}', file=sys.stderr)
        return 1
    print('审查结构、目标与引用校验通过；不代表审查结论正确。')
    return 0


if __name__ == '__main__':
    sys.exit(main())
