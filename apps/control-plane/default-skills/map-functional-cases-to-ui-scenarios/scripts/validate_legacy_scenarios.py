"""Validate literal oracle accounting and explicit stage-two handoff edges."""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import re
import unicodedata

STATUSES = {'ready','missing_page','missing_data','not_ui_testable','conflict'}
GAPS = {'missing_page','missing_data','not_ui_testable','unassertable_operator','conflict','requirement_only','case_only'}
OPERATORS = {'visible','text_eq','text_contains','url_eq','url_contains'}


def normalize_handoff(report, surface=None):
    """Unbound business intent is preferable to unverified executable bindings."""
    result=copy.deepcopy(report)
    changes=[]
    for scenario in result.get('scenarios',[]):
        if surface and surface.get('runtimeEvidence'):
            for plan in scenario.get('dataPlan',[]):
                refs=plan.get('evidenceRefs',[])
                for index,ref in enumerate(refs):
                    if not isinstance(ref,str) or not ref.startswith('/') or ref.startswith('/runtimeEvidence/'):
                        continue
                    try:
                        pointer(surface,ref)
                        continue
                    except (ValueError,KeyError,TypeError,IndexError):
                        pass
                    try:
                        pointer(surface['runtimeEvidence'],ref)
                    except (ValueError,KeyError,TypeError,IndexError):
                        continue
                    refs[index]='/runtimeEvidence'+ref
                    changes.append({'kind':'runtime_reference_path','scenarioId':scenario['scenarioId'],'from':ref,'to':refs[index]})
        if scenario.get('status')=='ready':
            continue
        actions=len(scenario.get('actionBindings',[]))
        checks=sum(len(b.get('checks',[])) for b in scenario.get('observationBindings',[]))
        scenario['actionBindings']=[]
        for binding in scenario.get('observationBindings',[]):
            binding['checks']=[]
        if actions or checks:
            changes.append({'scenarioId':scenario['scenarioId'],'removedActionBindings':actions,'removedUnverifiedChecks':checks})
    return result,changes


def normalize(text):
    text = re.sub(r'^\s*\d+(?:\.(?!\d)|[、．)])\s*','',str(text))
    return ''.join(c for c in text if not c.isspace() and (c in '-+/%<>=≤≥' or not unicodedata.category(c).startswith('P')))


def pointer(data, ref):
    for part in ref.lstrip('/').split('/'):
        part = part.replace('~1','/').replace('~0','~')
        data = data[int(part)] if isinstance(data,list) else data[part]
    return data


def validate(report, *, cases, surface, requirements=None, capabilities=None):
    errors = []
    def check(ok, message):
        if not ok:
            errors.append(message)

    source_cases = cases['cases'] if isinstance(cases,dict) else cases
    cases_by_id = {c['caseId']:c for c in source_cases}
    check(report.get('schemaVersion') == 'ui_test_scenarios/1.0','invalid schemaVersion')
    for key in ['scenarios','caseFrameworks','excludedExpectations','requirementGaps','coverage']:
        check(isinstance(report.get(key),list),f'missing array {key}')
    operators = set(capabilities or OPERATORS)
    elements = {}
    for name,key in [('pages','pageId'),('controls','controlId'),('containers','containerId'),('feedback','feedbackId'),('observedStates','stateId')]:
        elements.update({x[key]:x for x in surface.get(name,[])})
    page_ids = {p['pageId'] for p in surface.get('pages',[])}

    def proven(ident):
        target = elements.get(ident,{})
        if 'controlId' in target and target.get('uniqueness')!='confirmed':
            return False
        return ident in page_ids or any(x.get('confirmed') for x in target.get('locatorCandidates',[]))

    def evidence_exists(ref):
        if ref == 'taskContext' or ref in elements:
            return True
        try:
            pointer(surface,ref)
            return isinstance(ref,str) and ref.startswith('/')
        except (ValueError,KeyError,TypeError,IndexError):
            return False

    frames = {}
    expectations = {}
    records = {}
    excerpts = {}
    for frame in report.get('caseFrameworks',[]):
        cid = frame.get('functionCaseId')
        check(cid in cases_by_id and cid not in frames,f'invalid/duplicate framework {cid}')
        frames[cid] = frame
        check(bool(frame.get('caseGoal')),f'{cid}: missing caseGoal')
        check(bool(frame.get('coreExpectationIds')),f'{cid}: missing coreExpectationIds')
    collections = [('ui',[e|{'functionCaseId':f.get('functionCaseId')} for f in frames.values() for e in f.get('expectedResults',[])]),
                   ('excluded',report.get('excludedExpectations',[])),('bookkeeping',report.get('bookkeeping',[]))]
    for disposition,items in collections:
        for item in items:
            cid = item.get('functionCaseId')
            eid = item.get('expectationId')
            key = (cid,eid)
            check(cid in cases_by_id and bool(eid) and key not in records,f'invalid/duplicate expectation {key}')
            records[key] = item|{'collection':disposition}
            if disposition == 'ui':
                expectations[key] = item
                check(item.get('disposition') in ['executable','gap'],f'{key}: invalid disposition')
                if item.get('disposition') == 'gap':
                    check(item.get('gapCategory') in GAPS and bool(item.get('reason')),f'{key}: gap needs category/reason')
                else:
                    check(item.get('gapCategory') is None,f'{key}: executable still has a gap')
            elif disposition == 'excluded':
                check(item.get('reason','').startswith('not_ui_observable:'),f'{key}: invalid exclusion reason')
            elif disposition == 'bookkeeping':
                check(bool(item.get('reason')),f'{key}: bookkeeping needs a reason')
            steps = item.get('sourceStepNos',[])
            check(len(steps)==1 and isinstance(steps[0],int),f'{key}: use exactly one sourceStepNos entry')
            quote = item.get('sourceQuote')
            check(bool(quote) and item.get('text') == quote,f'{key}: text must equal the verbatim sourceQuote')
            if cid not in cases_by_id or len(steps)!=1 or not isinstance(steps[0],int):
                continue
            source_steps = cases_by_id[cid]['content']['steps']
            if not 1 <= steps[0] <= len(source_steps):
                check(False,f'{key}: invalid source step')
                continue
            expected = source_steps[steps[0]-1]['expected']
            check(bool(quote) and quote in expected,f'{key}: sourceQuote was invented/paraphrased')
            excerpts.setdefault((cid,steps[0]),[]).append((key,normalize(quote or '')))

    for cid,case in cases_by_id.items():
        for n,step in enumerate(case['content']['steps'],1):
            original = normalize(step['expected'])
            occupied = [False]*len(original)
            for key,quote in excerpts.get((cid,n),[]):
                if not quote:
                    continue
                offset = original.find(quote)
                while offset >= 0 and any(occupied[offset:offset+len(quote)]):
                    offset = original.find(quote,offset+1)
                if offset < 0:
                    check(False,f'{key}: duplicate/overlapping source excerpts')
                else:
                    occupied[offset:offset+len(quote)] = [True]*len(quote)
            missing = ''.join(c for c,used in zip(original,occupied) if not used)
            check(not missing,f'{cid} step {n}: unaccounted source text: {missing[:100]}')

    scenarios = {}
    asserted = {}
    ready_by_case = {cid:[] for cid in cases_by_id}
    for scenario in report.get('scenarios',[]):
        sid = scenario.get('scenarioId')
        check(bool(re.fullmatch(r'S\d{3,}',sid or '')) and sid not in scenarios,f'invalid/duplicate scenario {sid}')
        scenarios[sid] = scenario
        sources = scenario.get('sourceFunctionCaseIds',[])
        check(bool(sources) and set(sources)<=set(cases_by_id),f'{sid}: invalid source cases')
        status = scenario.get('status')
        check(status in STATUSES,f'{sid}: invalid status')
        ready = status == 'ready'
        check(scenario.get('gapCategory') is None if ready else scenario.get('gapCategory') in GAPS,f'{sid}: invalid gapCategory')
        goal = scenario.get('goalCheck',{})
        check(bool(goal.get('incorrectBehavior')) and bool(goal.get('explanation')),f'{sid}: missing goalCheck')
        if ready:
            check(scenario.get('uiAssertability') in ['ui','partial'],f'{sid}: invalid uiAssertability')
            check(bool(scenario.get('requiredObservations')),f'{sid}: no observations')
            for cid in sources:
                if cid in ready_by_case:
                    ready_by_case[cid].append(sid)

        expected_preconditions = {(cid,f'P{i:02}') for cid in sources if cid in cases_by_id
                                  for i,_ in enumerate(cases_by_id[cid]['content'].get('preconditions',[]),1)}
        supplied_preconditions = [(p.get('functionCaseId'),p.get('preconditionId')) for p in scenario.get('preconditionRefs',[])]
        check(set(supplied_preconditions)==expected_preconditions and len(supplied_preconditions)==len(expected_preconditions),f'{sid}: original preconditions missing/duplicated')
        plans = {(p.get('functionCaseId'),p.get('preconditionId')):p for p in scenario.get('dataPlan',[])}
        check(set(plans)==expected_preconditions,f'{sid}: incomplete dataPlan')
        for pre,p in plans.items():
            data_status = p.get('status')
            check(data_status in ['given_fixture','ui_preparable','bookkeeping','needs_input'],f'{sid}: invalid dataPlan status')
            check(bool(p.get('reason')),f'{sid}: dataPlan lacks reason')
            if ready:
                check(data_status!='needs_input',f'{sid}: ready despite missing essential precondition {pre}')
            if data_status=='given_fixture':
                refs = p.get('evidenceRefs',[])
                check(bool(refs) and all(evidence_exists(x) for x in refs),f'{sid}: ungrounded fixture {pre}')
            if data_status=='ui_preparable':
                ids = p.get('controlIds',[])
                check(bool(ids) and all(proven(x) for x in ids),f'{sid}: UI preparation lacks confirmed controls {pre}')
            if data_status=='bookkeeping' and pre[0] in cases_by_id:
                text = cases_by_id[pre[0]]['content']['preconditions'][int(pre[1][1:])-1]
                check(bool(re.match(r'^(?:\d+[.、)]\s*)?(?:已记录|记录|record)',text,re.I)),f'{sid}: essential condition reclassified as bookkeeping {pre}')

        actions = scenario.get('requiredActions',[])
        if not ready:
            check(not scenario.get('actionBindings'),f'{sid}: non-ready intent must not carry executable action bindings')
        action_indices=[]
        for b in scenario.get('actionBindings',[]):
            action_indices.append(b.get('actionIndex'))
            check(isinstance(b.get('actionIndex'),int) and 1<=b['actionIndex']<=len(actions),f'{sid}: invalid action binding index')
            ids = b.get('controlIds',[])+b.get('pageIds',[])
            check(set(ids)<=set(elements),f'{sid}: unknown action target')
            if ready:
                check(bool(ids) and all(proven(x) for x in ids),f'{sid}: action target unconfirmed')
                operation=b.get('operation')
                check(operation in ['navigate','activate','input','select','observe','wait','sequence'],f'{sid}: action operation missing')
                selectors=[x for x in b.get('controlIds',[]) if elements.get(x,{}).get('controlType','').lower()=='select']
                action=actions[b['actionIndex']-1] if isinstance(b.get('actionIndex'),int) and 1<=b['actionIndex']<=len(actions) else ''
                positive_selection=bool(re.search(r'选择|选中|\bselect\b|\bchoose\b',action,re.I)) and not re.search(r'未选择|不选择|未选|不选|保持为空|保持未|without selecting|unselected',action,re.I)
                if selectors and (operation=='select' or positive_selection):
                    selected={s.get('controlId'):s for s in b.get('selectedOptions',[])}
                    check(set(selectors)<=set(selected),f'{sid}: selected field is not proof of an addressable option')
                    for control in selectors:
                        choice=selected.get(control,{})
                        option=choice.get('optionControlId')
                        allowed={o.get('controlId') for o in elements[control].get('options',[]) if o.get('availability')=='addressable'}
                        check(option in allowed and option!=control and proven(option),f'{sid}: selection option is unconfirmed')
        if ready:
            check(sorted(action_indices)==list(range(1,len(actions)+1)),f'{sid}: actions not all bound exactly once')

        observations = scenario.get('requiredObservations',[])
        observation_indices=[]
        bound_by_case = {cid:set() for cid in sources}
        for b in scenario.get('observationBindings',[]):
            index = b.get('observationIndex')
            observation_indices.append(index)
            check(isinstance(index,int) and 1<=index<=len(observations),f'{sid}: invalid observation binding index')
            cid = b.get('functionCaseId')
            eids = b.get('expectationIds',[])
            keys = [(cid,eid) for eid in eids]
            check(cid in sources and bool(eids) and all(k in expectations for k in keys),f'{sid}: invalid expectation binding')
            text = '\n'.join(expectations[k]['text'] for k in keys if k in expectations)
            if isinstance(index,int) and 1<=index<=len(observations):
                check(normalize(observations[index-1])==normalize(text),f'{sid}: observation rewrites its source oracle')
            for key in keys:
                if cid in bound_by_case:
                    bound_by_case[cid].add(key[1])
                if ready and key in expectations:
                    check(expectations[key].get('disposition')=='executable',f'{sid}: ready observation contains gap {key}')
                    asserted.setdefault(key,set()).add(sid)
            concrete=b.get('checks',[])
            if not ready:
                check(not concrete,f'{sid}: non-ready intent must not carry unverified assertion checks')
            if ready:
                check(bool(concrete),f'{sid}: observation has no concrete assertion checks')
            for assertion in concrete:
                target=assertion.get('targetId')
                check(target in elements,f'{sid}: unknown assertion target')
                if not ready:
                    continue
                operator=assertion.get('operator')
                check(operator in operators,f'{sid}: unsupported assertion operator')
                check(proven(target),f'{sid}: assertion target unconfirmed')
                if operator in ['text_eq','text_contains']:
                    el=elements.get(target,{})
                    check(el.get('controlType','').lower() not in ['input','textarea','textinput','numberinput','passwordinput'] and el.get('role') not in ['textbox','searchbox'],f'{sid}: input value cannot be asserted with DOM textContent')
                if operator and operator.startswith('url_'):
                    check(target in page_ids,f'{sid}: URL assertion must bind pages')
                if operator!='visible':
                    expected=assertion.get('expectedText')
                    check(isinstance(expected,str) and bool(expected),f'{sid}: missing literal expectedText')
                    if not isinstance(expected,str) or not expected:
                        continue
                    el=elements.get(target,{})
                    direct=expected in [el.get('visibleText'),el.get('text'),el.get('route')]
                    quoted=set()
                    for group in re.findall(r'“([^”]+)”|"([^"\n]+)"|【([^】]+)】',text):
                        quoted.update(x for x in group if x)
                    numeric=set(re.findall(r'[+-]?\d+(?:\.\d+)?',text))
                    literal=expected in quoted or expected in numeric
                    vars_used=re.findall(r'\{\{([A-Za-z0-9_.]+)\}\}',expected)
                    variable=bool(vars_used) and all(v in scenario.get('variables',{}) for v in vars_used)
                    referenced=False
                    for ref in assertion.get('valueRefs',[]):
                        try:
                            value=pointer(surface,ref)
                            if isinstance(value,(str,int,float)) and str(value)==expected:referenced=True
                        except (KeyError,ValueError,IndexError,TypeError):
                            check(False,f'{sid}: invalid value evidence reference')
                    check(direct or literal or variable or referenced,f'{sid}: assertion uses an ungrounded expected value or business sentence')
        if ready:
            check(sorted(observation_indices)==list(range(1,len(observations)+1)),f'{sid}: observations not all bound exactly once')
            for cid in sources:
                core = frames.get(cid,{}).get('coreExpectationIds',[])
                check(bool(core) and set(core)<=bound_by_case.get(cid,set()),f'{sid}: ready core drops the primary goal of {cid}')
            detected = set(goal.get('detectedByExpectationIds',[]))
            check(bool(detected) and detected <= set().union(*bound_by_case.values()),f'{sid}: goalCheck is not bound to actual observations')

        if status=='conflict':
            conflicts = scenario.get('conflictEvidence',[])
            check(bool(conflicts),f'{sid}: conflict has no comparable evidence')
            for conflict in conflicts:
                key = (conflict.get('functionCaseId'),conflict.get('expectationId'))
                check(key in records and conflict.get('expectedQuote')==records.get(key,{}).get('sourceQuote'),f'{sid}: conflict oracle mismatch')
                check(bool(conflict.get('observedFact')),f'{sid}: conflict lacks observed fact')
                if conflict.get('kind')=='source':
                    check(bool(conflict.get('sourceRefs')),f'{sid}: source conflict lacks source references')
                    check(all(re.fullmatch(r'.+:\d+', ref or '') for ref in conflict.get('sourceRefs',[])),f'{sid}: source conflict sourceRefs must be file:line, not requirement prose')
                elif conflict.get('kind')=='runtime':
                    targets = conflict.get('targetIds',[])
                    objects=[]
                    for target in targets:
                        candidates=elements.get(target,{}).get('locatorCandidates',[])
                        runtime=[x for x in candidates if x.get('evidenceType')=='runtime' and x.get('confirmed')]
                        objects += [(x.get('context') or {}).get('object') for x in runtime]
                        check(bool(runtime),f'{sid}: runtime comparison lacks a proven target')
                    check(bool(objects) and all(objects) and len(set(objects))==1,f'{sid}: runtime conflict joins unrelated/unidentified objects')
                else:
                    check(False,f'{sid}: invalid conflict kind')

    for key,item in expectations.items():
        scenario_ids = item.get('scenarioIds',[])
        check(set(scenario_ids)<=set(scenarios),f'{key}: dangling scenario reference')
        if item.get('disposition')=='executable':
            check(bool(asserted.get(key)),f'{key}: executable has no ready assertion')
            check(asserted.get(key,set())<=set(scenario_ids),f'{key}: scenario references omit asserting scenario')
    for cid,frame in frames.items():
        check(all((cid,eid) in records for eid in frame.get('coreExpectationIds',[])),f'{cid}: unresolved core expectations')
        values=frame.get('expectedResults',[])
        executable=sum(e.get('disposition')=='executable' for e in values)
        state='complete' if executable==len(values) and values else 'partial' if executable else 'blocked'
        check(frame.get('frameStatus')==state,f'{cid}: incorrect frameStatus, expected {state}')
    coverage={}
    for item in report.get('coverage',[]):
        cid=item.get('functionCaseId')
        check(cid in cases_by_id and cid not in coverage,f'invalid/duplicate coverage {cid}')
        coverage[cid]=item
        related={sid for sid,s in scenarios.items() if cid in s.get('sourceFunctionCaseIds',[])}
        check(set(item.get('scenarioIds',[]))==related,f'{cid}: coverage scenario list mismatch')
        if cid in frames:
            state=frames[cid]['frameStatus']
            check(item.get('frameStatus')==state,f'{cid}: coverage/frame disagree')
            if state=='complete':
                check(item.get('status')=='ready',f'{cid}: complete UI frame must have ready coverage')
            elif state=='partial':
                check(item.get('status')=='partial' and bool(ready_by_case.get(cid)),f'{cid}: partial coverage lacks valid core')
            else:
                check(item.get('status') in STATUSES-{'ready'} and not ready_by_case.get(cid),f'{cid}: blocked case has ready/partial coverage')
        else:
            check(item.get('frameStatus')=='excluded' and item.get('status')=='not_ui_testable',f'{cid}: no frame needs excluded coverage')
            check(any(k[0]==cid and r['collection']=='excluded' for k,r in records.items()),f'{cid}: missing exclusion accounting')
    check(set(coverage)==set(cases_by_id),'selected cases missing from coverage')
    if requirements:
        allowed_s={s['scenarioId'] for s in requirements.get('scenarios',[])}
        allowed_r={r['ruleId'] for r in requirements.get('rules',[])}
        allowed_e={r['id'] for k in ['sources','evidence'] for r in requirements.get(k,[]) if r.get('id')}
        for sid,s in scenarios.items():
            check(set(s.get('requirementScenarioIds',[]))<=allowed_s,f'{sid}: unknown requirement scenario')
            check(set(s.get('relatedRuleIds',[]))<=allowed_r,f'{sid}: unknown requirement rule')
            check(set(s.get('requirementRefs',[]))<=allowed_e,f'{sid}: unknown requirement evidence')
        for gap in report.get('requirementGaps',[]):
            check(gap.get('requirementScenarioId') in allowed_s and set(gap.get('relatedRuleIds',[]))<=allowed_r,'unknown requirement gap reference')
    return errors


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('artifact',type=Path)
    parser.add_argument('--cases',type=Path,required=True)
    parser.add_argument('--surface',type=Path,required=True)
    parser.add_argument('--requirements',type=Path)
    parser.add_argument('--finalize',action='store_true',help='Remove tentative bindings from non-ready intent before validation')
    args=parser.parse_args()
    artifact=json.loads(args.artifact.read_text())
    surface=json.loads(args.surface.read_text())
    if args.finalize:
        artifact,changes=normalize_handoff(artifact,surface)
    errors=validate(artifact,cases=json.loads(args.cases.read_text()),surface=surface,requirements=json.loads(args.requirements.read_text()) if args.requirements else None)
    if errors:
        raise SystemExit('\n'.join(errors))
    if args.finalize:
        args.artifact.write_text(json.dumps(artifact,ensure_ascii=False,indent=2)+'\n')
        print(json.dumps({'removedTentativeBindings':changes},ensure_ascii=False))
    print('source accounting, preconditions, core, bindings and consistency checks passed')


if __name__=='__main__':
    main()
