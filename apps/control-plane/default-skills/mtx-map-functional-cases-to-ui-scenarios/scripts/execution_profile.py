"""Versioned execution features, separate from the unchanged scenario/YAML outputs."""
import json
from pathlib import Path

FEATURES = {'xpathPredicates', 'scalarCapture', 'variableSubstitution', 'conditionalFlow', 'runtimeIteration', 'crossCasePreflight'}


def load_profile(path=None):
    path = Path(path) if path else Path(__file__).resolve().parent.parent / 'references/execution-profile.json'
    profile = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(profile, dict):
        raise ValueError('execution profile must be an object')
    if profile.get('schemaVersion') != 'ui_execution_profile/1.0' or not isinstance(profile.get('profileId'), str) or not profile['profileId'].strip():
        raise ValueError('unknown execution profile schema or missing profileId')
    features = profile.get('features', {})
    if not isinstance(features, dict) or set(features) != FEATURES or any(type(v) is not bool for v in features.values()):
        raise ValueError('execution profile must explicitly declare all boolean features')
    capabilities = profile.get('capabilities', {})
    if not isinstance(capabilities, dict):
        raise ValueError('capabilities must be an object')
    for key in ('operations', 'assertions'):
        values = capabilities.get(key)
        if not isinstance(values, list) or any(not isinstance(v, str) or not v.strip() for v in values) or len(values) != len(set(values)):
            raise ValueError('invalid execution profile capabilities.' + key)
    sources = profile.get('captureSources')
    if not isinstance(sources, list) or any(v not in ('text', 'value', 'attribute', 'url') for v in sources) or len(sources) != len(set(sources)):
        raise ValueError('invalid captureSources')
    return profile


def candidate_feature_errors(rows, profile):
    errors = []
    f = profile['features']
    for ci, case in enumerate(rows, 1):
        for step in case['stepsJson']:
            label = f"case {ci}/step {step.get('orderNo')}"
            rules = step.get('saveTo', [])
            if not isinstance(rules, list) or any(not isinstance(rule, dict) for rule in rules):
                errors.append(label + ': invalid saveTo rules')
                continue
            if rules and not f['scalarCapture']:
                errors.append(label + ': scalar capture disabled by execution profile')
            for rule in rules:
                if rule.get('source') not in profile['captureSources']:
                    errors.append(label + ': unsupported capture source')
            for obj in [step, *rules]:
                if not f['xpathPredicates'] and obj.get('locatorType') == 'xpath' and '[' in str(obj.get('locatorValue', '')):
                    errors.append(label + ': XPath predicates disabled by execution profile')
                if not f['variableSubstitution'] and any('{{' in str(obj.get(key, '')) for key in ('locatorValue', 'operationValue')):
                    errors.append(label + ': variable substitution disabled by execution profile')
    return errors
