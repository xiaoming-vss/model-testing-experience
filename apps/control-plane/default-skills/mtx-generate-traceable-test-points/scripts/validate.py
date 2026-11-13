#!/usr/bin/env python3
"""Validate three artifact schemas, unique IDs and cross-artifact references."""
import json
import sys
from pathlib import Path

try:
    import jsonschema
except ImportError:
    sys.exit('缺少依赖：请安装 jsonschema；未完成校验。')

from material_checks import validate_material
from review_checks import validate_issues

ROOT = Path(__file__).resolve().parent.parent

def read(path):
    def no_duplicates(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f'重复 JSON 键: {key}')
            result[key] = value
        return result
    return json.loads(Path(path).read_text(encoding='utf-8'), object_pairs_hook=no_duplicates)

def validate_artifacts(material, scope, output):
    for artifact, schema_name in zip((material, scope, output), ('material.schema.json', 'scope.schema.json', 'output.schema.json')):
        schema = read(ROOT / 'references' / schema_name)
        jsonschema.Draft202012Validator.check_schema(schema)
        jsonschema.Draft202012Validator(schema).validate(artifact)
    errors = validate_material(material, read(ROOT / "references/material.schema.json"))
    def collect(artifact, field, label):
        values = [entry['id'] for entry in artifact[field]]
        if len(values) != len(set(values)):
            errors.append(f'{label} ID 重复')
        return set(values)
    blocks = collect(material, 'materialBlocks', '材料块')
    mq = collect(material, 'questions', '材料问题')
    objects = collect(scope, 'testObjects', '测试对象')
    impacts = collect(scope, 'impactAreas', '影响范围')
    risks = collect(scope, 'risks', '风险')
    sq = collect(scope, 'openQuestions', '分析问题')
    collect(output, 'testPoints', '测试点')
    collect(output, 'coverageGaps', '覆盖缺口')
    def refs(entry, field, allowed, label):
        unknown = set(entry.get(field, [])) - allowed
        if unknown:
            errors.append(f'{label}.{field} 引用不存在: {sorted(unknown)}')
    targets = {'sourceBlockIds':blocks, 'sourceQuestionIds':mq, 'testObjectIds':objects, 'impactAreaIds':impacts, 'riskIds':risks}
    for field in ('testObjects', 'impactAreas', 'risks', 'openQuestions'):
        for entry in scope[field]:
            for key, allowed in targets.items(): refs(entry, key, allowed, f"{field} {entry['id']}")
    for point in output['testPoints']:
        prefix = '【' + point['module'] + '】'
        if not point['name'].startswith(tuple(prefix + word for word in ('验证', '测量', '观察'))):
            errors.append(f"测试点 {point['id']} 名称须以【功能项】和验证、测量或观察开头")
        if point['name'].startswith((prefix + '测量', prefix + '观察')) and point['dimension'] not in ('性能场景', '长稳场景'):
            errors.append(f"测试点 {point['id']} 测量或观察仅适用于性能或长稳基线")
    targets = {'materialBlockIds':blocks, 'testObjectIds':objects, 'impactAreaIds':impacts, 'riskIds':risks, 'materialQuestionIds':mq, 'scopeQuestionIds':sq}
    for field in ('testPoints', 'coverageGaps'):
        for entry in output[field]:
            for key, allowed in targets.items(): refs(entry, key, allowed, f"{field} {entry['id']}")
    errors.extend(validate_issues(output.get('reviewIssues', []), material, scope, output))
    if output['reviewStatus'] == 'independent_reviewed' and output.get('reviewIssues'):
        errors.append('independent_reviewed 不能包含未解决的 reviewIssues')
    return errors


def main():
    if len(sys.argv) != 4:
        print('用法: validate.py <材料.json> <范围分析.json> <结果.json>', file=sys.stderr)
        return 2
    try:
        errors = validate_artifacts(*(read(path) for path in sys.argv[1:]))
        if errors:
            raise ValueError('\n'.join(errors))
    except (OSError, ValueError, KeyError, TypeError, jsonschema.ValidationError, jsonschema.SchemaError) as exc:
        print(f'校验失败: {exc}', file=sys.stderr)
        return 1
    print('结构、ID、引用和审查状态一致性校验通过；不代表版本配套、实际审核完成、语义正确或覆盖完整。')
    return 0


if __name__ == '__main__':
    sys.exit(main())
