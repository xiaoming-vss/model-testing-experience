"""Validate provenance and inspection coverage; never invent UI facts."""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import re


def pointer(value, ref):
    if not isinstance(ref, str) or not ref.startswith('/'):
        raise ValueError('evidence reference must be a JSON pointer')
    for part in ref[1:].split('/'):
        part = part.replace('~1', '/').replace('~0', '~')
        value = value[int(part)] if isinstance(value, list) else value[part]
    return value


def cases_list(value):
    return value['cases'] if isinstance(value, dict) else value


def generated_class(value):
    return bool(re.search(r'contains\s*\(\s*@class|\.(?:n|ant|el|arco)-', value))


def normalize_surface(surface):
    """Keep descriptive facts out of concrete-locator/literal-message fields."""
    result=copy.deepcopy(surface)
    changes=[]
    for item in result.get('containers',[]):
        row=item.get('rowLocator')
        if isinstance(row,dict) and not row.get('locatorValue') and row.get('description'):
            item['rowKey']=row
            item['rowLocator']=None
            changes.append({'kind':'row_key_description','id':item['containerId']})
    feedback=[]
    for item in result.get('feedback',[]):
        if not item.get('text'):
            state=dict(item,stateId=item['feedbackId'])
            result.setdefault('observedStates',[]).append(state)
            changes.append({'kind':'non_message_state','id':item['feedbackId']})
        else:
            feedback.append(item)
    result['feedback']=feedback
    for item in result.get('interactions',[]):
        effect=item.get('effect','')
        if len(effect)>60:
            item['description']=effect
            short=re.split(r'[（；;,，]',effect,maxsplit=1)[0].strip()
            item['effect']=short if 0<len(short)<=60 else 'described_interaction'
            changes.append({'kind':'interaction_description','id':item['interactionId']})
    return result,changes


def validate(surface, *, source_root=None, cases=None, runtime=None):
    errors = []
    def check(ok, message):
        if not ok:
            errors.append(message)

    check(surface.get('schemaVersion') == 'ui_test_surface/1.0', 'invalid schemaVersion')
    for name in ['app','pages','containers','controls','feedback','interactions','unknowns','inspectionCoverage','evidenceIssues']:
        check(name in surface, f'missing {name}')
    root = Path(source_root).resolve() if source_root else None
    if runtime is None:
        runtime = surface.get('runtimeEvidence')
    elif 'runtimeEvidence' in surface:
        check(surface['runtimeEvidence'] == runtime, 'raw runtimeEvidence was changed')

    def source_ref(ref, label):
        match = re.fullmatch(r'(.+):(\d+)', ref or '')
        check(bool(match), f'{label}: expected one file:line sourceRef')
        if not match or not root:
            return
        path = (root/match[1]).resolve()
        check(path.is_relative_to(root) and path.is_file(), f'{label}: source file missing/outside sourceRoot')
        if path.is_file() and path.is_relative_to(root):
            lines = len(path.read_text(encoding='utf-8').splitlines())
            check(1 <= int(match[2]) <= lines, f'{label}: source line out of range')

    by_id = {}
    page_ids = {p.get('pageId') for p in surface.get('pages',[])}
    check(bool(page_ids), 'no pages extracted')
    fields = [('pages','pageId'),('containers','containerId'),('controls','controlId'),('feedback','feedbackId'),('observedStates','stateId')]
    for array,key in fields:
        for item in surface.get(array,[]):
            ident = item.get(key)
            check(bool(ident) and ident not in by_id, f'duplicate/missing element id {ident}')
            by_id[ident] = item
            source_ref(item.get('sourceRef'),str(ident))
            if array=='containers' and item.get('rowLocator') is not None:
                row=item['rowLocator']
                check(bool(row.get('locatorType')) and bool(row.get('locatorValue')),f'{ident}: rowLocator must be a concrete locator; descriptive keys belong in rowKey')
            if array=='feedback':
                check(bool(item.get('text')),f'{ident}: non-message capture belongs in observedStates')
            if array != 'pages':
                check(item.get('pageId') in page_ids, f'{ident}: unknown pageId')
            if array == 'controls':
                check(item.get('uniqueness') in ['confirmed','unknown'], f'{ident}: invalid uniqueness')
                if item.get('uniqueness') == 'confirmed':
                    check(any(l.get('confirmed') for l in item.get('locatorCandidates',[])), f'{ident}: confirmed without a proven candidate')
                dynamic=item.get('role')=='cell' or item.get('controlType','').lower() in ['readonlytext','readonly_text','table_cell','select']
                if dynamic and item.get('visibleText'):
                    try:
                        sample=pointer(runtime,item.get('sampleValueRef'))
                        check(item.get('sampleOnly') is True and isinstance(sample,(str,int,float)) and str(sample)==item['visibleText'],f'{ident}: dynamic visibleText must be a captured value, not a field caption')
                    except (ValueError,KeyError,IndexError,TypeError,AttributeError):
                        check(False,f'{ident}: dynamic visibleText lacks scalar sample provenance')
            for loc in item.get('locatorCandidates',[]):
                check(bool(loc.get('locatorType')) and bool(loc.get('locatorValue')), f'{ident}: empty locator')
                check(loc.get('evidenceType') in ['source','runtime'], f'{ident}: missing evidenceType')
                check(isinstance(loc.get('context'),dict), f'{ident}: missing context')
                if loc.get('evidenceType') == 'source':
                    source_ref(loc.get('sourceRef'),f'{ident} locator')
                    check(not generated_class(loc.get('locatorValue','')), f'{ident}: source-only generated-class locator')
                    check(bool(loc.get('reason')), f'{ident}: source candidate has no proof reason')
                elif loc.get('evidenceType') == 'runtime':
                    try:
                        proof = pointer(runtime,loc.get('runtimeEvidenceRef'))
                        check(proof.get('count') == 1, f'{ident}: runtime count is not 1')
                        check(all(proof.get(k) == loc.get(k) for k in ['locatorType','locatorValue']), f'{ident}: runtime locator was rewritten')
                        obj = (loc.get('context') or {}).get('object')
                        if obj:
                            value = obj.split('=',1)[-1]
                            check(value in json.dumps(proof,ensure_ascii=False), f'{ident}: object context is not supported by locator entry')
                    except (ValueError,KeyError,IndexError,TypeError,AttributeError):
                        check(False,f'{ident}: invalid runtime evidence pointer')
                    if generated_class(loc.get('locatorValue','')):
                        check(loc.get('stability') == 'runtime_only', f'{ident}: runtime generated-class candidate must be runtime_only')

    container_ids = {c.get('containerId') for c in surface.get('containers',[])}
    for c in surface.get('controls',[]):
        if c.get('containerId'):
            check(c['containerId'] in container_ids,f'{c.get("controlId")}: dangling containerId')
        if c.get('controlType','').lower()=='select':
            check(isinstance(c.get('options'),list),f'{c.get("controlId")}: select must declare option evidence (possibly empty)')
            for option in c.get('options',[]):
                if option.get('availability')=='addressable':
                    target=by_id.get(option.get('controlId'),{})
                    check(target.get('uniqueness')=='confirmed' and any(x.get('confirmed') for x in target.get('locatorCandidates',[])),f'{c.get("controlId")}: addressable option lacks a confirmed option control')
    interaction_ids = set()
    for item in surface.get('interactions',[]):
        ident = item.get('interactionId')
        check(bool(ident) and ident not in interaction_ids,f'duplicate/missing interaction {ident}')
        interaction_ids.add(ident)
        check(item.get('pageId') in page_ids,f'{ident}: unknown page')
        check(item.get('controlId') in by_id,f'{ident}: unknown control')
        check(item.get('targetId') in by_id,f'{ident}: unknown interaction target')
        source_ref(item.get('sourceRef'),str(ident))

    selected = {c['caseId'] for c in cases_list(cases)} if cases is not None else None
    covered = set()
    inspected_files = set()
    for entry in surface.get('inspectionCoverage',[]):
        covered.update(entry.get('caseIds',[]))
        status = entry.get('status')
        check(status in ['inspected','unavailable','non_ui'],f'{entry.get("area")}: invalid inspection status')
        if status == 'inspected':
            check(bool(entry.get('componentFiles')),f'{entry.get("area")}: no inspected files')
            for name in entry.get('componentFiles',[]):
                inspected_files.add(name)
                if root:
                    check((root/name).is_file(),f'{entry.get("area")}: inspected file missing: {name}')
            check(set(entry.get('pageIds',[])) <= page_ids,f'{entry.get("area")}: unknown inspection page')
        else:
            check(bool(entry.get('reason')),f'{entry.get("area")}: inspection explanation missing')
    if selected is not None:
        check(covered == selected,f'inspection case coverage mismatch: missing={sorted(selected-covered)}, extra={sorted(covered-selected)}')
    for page in surface.get('pages',[]):
        check(page.get('componentFile') in inspected_files,f'{page.get("pageId")}: component missing from inspected files')
    for unknown in surface.get('unknowns',[]):
        reason = unknown.get('reason','').lower()
        check(not any(t in reason for t in ['未检查','未在本次检查','not inspected','not read yet']),f'{unknown.get("topic")}: accessible scope left uninspected')
    for item in surface.get('unknowns',[])+surface.get('evidenceIssues',[]):
        prose=item.get('topic','')+' '+item.get('reason','')
        check(not re.search(r'用例.{0,50}(?:期望|预期|用词|要求)|(?:期望|预期).{0,50}用例',prose),'surface mixes formal-case oracle comparison into UI evidence')
    return errors


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('artifact',type=Path)
    parser.add_argument('--source-root')
    parser.add_argument('--cases',type=Path)
    parser.add_argument('--runtime-evidence',type=Path)
    parser.add_argument('--finalize',action='store_true')
    args = parser.parse_args()
    data = json.loads(args.artifact.read_text())
    changes=[]
    if args.finalize:
        data,changes=normalize_surface(data)
    runtime = json.loads(args.runtime_evidence.read_text()) if args.runtime_evidence else None
    cases = json.loads(args.cases.read_text()) if args.cases else None
    errors = validate(data,source_root=args.source_root,cases=cases,runtime=runtime)
    if errors:
        raise SystemExit('\n'.join(errors))
    if args.finalize:
        if runtime is not None:
            data['runtimeEvidence'] = runtime
        args.artifact.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
    if changes:
        print(json.dumps({'normalizedMetadata':changes},ensure_ascii=False))
    print('surface provenance and inspection checks passed')


if __name__ == '__main__':
    main()
