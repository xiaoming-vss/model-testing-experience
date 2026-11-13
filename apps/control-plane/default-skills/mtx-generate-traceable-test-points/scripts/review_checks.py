"""Check review issue targets and evidence in candidates or a review phase."""
import json
from pathlib import Path

from jsonschema import Draft202012Validator

FIELDS = {
    'materialBlockIds': ('materialBlocks', 'material'),
    'testObjectIds': ('testObjects', 'scope'),
    'impactAreaIds': ('impactAreas', 'scope'),
    'riskIds': ('risks', 'scope'),
    'materialQuestionIds': ('questions', 'material'),
    'scopeQuestionIds': ('openQuestions', 'scope'),
}
TARGETS = {
    'basis': {'testPoint'},
    'coverage': {'testPoint', 'missing'},
    'gaps': {'coverageGap', 'missing'},
}


def validate_issues(issues, material, scope, candidate, phase=None, batch=None):
    schema = json.loads((Path(__file__).resolve().parent.parent / 'references/output.schema.json').read_text(encoding='utf-8'))
    issue_schema = {'$defs': schema['$defs'], 'type': 'array', 'items': {'$ref': '#/$defs/reviewIssue'}}
    errors = [f'reviewIssues/{e.json_path}: {e.message}' for e in Draft202012Validator(issue_schema).iter_errors(issues)]
    if errors:
        return errors
    points = {point['id'] for point in candidate['testPoints']}
    gaps = {gap['id'] for gap in candidate['coverageGaps']}
    if phase is not None and phase not in TARGETS:
        return ['审查阶段无效']
    if phase == 'basis':
        if (not isinstance(batch, list) or not 1 <= len(batch) <= 10
                or any(not isinstance(v, str) or not v.strip() for v in batch)
                or len(batch) != len(set(batch)) or not set(batch) <= points):
            return ['依据审查的每个子批次必须包含 1 至 10 个不同的有效测试点 ID；请拆批后分别校验']
        points = set(batch)
    elif batch is not None:
        return ['只有依据审查使用批次 ID']
    sources = {'material': material, 'scope': scope}
    valid_ids = {field: {entry['id'] for entry in sources[origin][name]}
                 for field, (name, origin) in FIELDS.items()}
    for index, issue in enumerate(issues, 1):
        label = f'审查问题 {index}'
        target_type, target = issue['targetType'], issue['targetId']
        if phase is not None and target_type not in TARGETS[phase]:
            errors.append(f'{label}: 目标类型与审查阶段不匹配')
        if target_type == 'missing':
            if target is not None or issue['kind'] != 'missing':
                errors.append(f'{label}: 遗漏目标须为 null 且 kind 为 missing')
        elif target not in (points if target_type == 'testPoint' else gaps):
            errors.append(f'{label}: 目标不存在或不在本批')
        for field, allowed in valid_ids.items():
            unknown = set(issue[field]) - allowed
            if unknown:
                errors.append(f'{label}.{field}: 引用不存在 {sorted(unknown)}')
        if not any(issue[field] for field in FIELDS):
            errors.append(f'{label}: 缺少任何输入引用')
    return errors
