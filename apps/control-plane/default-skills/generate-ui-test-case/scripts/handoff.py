"""Evidence and coverage checks for the internal handoff; no platform fields added."""
from __future__ import annotations

import copy
from pathlib import Path
import re
from urllib.parse import urlparse


class HandoffError(ValueError):
    pass


def need(ok, message):
    if not ok:
        raise HandoffError(message)


def pointer(value, ref):
    need(isinstance(ref,str) and ref.startswith('/'), 'invalid JSON pointer')
    for part in ref[1:].split('/'):
        part=part.replace('~1','/').replace('~0','~')
        value=value[int(part)] if isinstance(value,list) else value[part]
    return value


def elements(bundle):
    surface=bundle['surface']
    return {item[key]:item for array,key in [('pages','pageId'),('controls','controlId'),('containers','containerId'),('feedback','feedbackId'),('observedStates','stateId')] for item in surface.get(array,[])}


def source_ref(bundle, ref):
    match=re.fullmatch(r'(.+):(\d+)',ref or '')
    need(match is not None,'source evidence requires one file:line')
    if bundle.get('sourceRoot'):
        root=Path(bundle['sourceRoot']).resolve();path=(root/match[1]).resolve()
        need(path.is_relative_to(root) and path.is_file(),'source evidence outside/missing sourceRoot')
        need(1<=int(match[2])<=len(path.read_text().splitlines()),'source line out of range')


def usable_candidates(bundle, target):
    item=elements(bundle).get(target)
    need(item is not None,f'unknown target {target}')
    if 'controlId' in item:
        need(item.get('uniqueness')=='confirmed',f'unconfirmed target {target}')
    candidates=[]
    for loc in item.get('locatorCandidates',[]):
        if not loc.get('confirmed'):
            continue
        need(bool(loc.get('locatorType')) and bool(loc.get('locatorValue')),'empty locator')
        if loc.get('evidenceType')=='runtime':
            try:
                proof=pointer(bundle['surface']['runtimeEvidence'],loc.get('runtimeEvidenceRef'))
            except (HandoffError,KeyError,IndexError,ValueError,TypeError) as exc:
                raise HandoffError(f'{target}: missing raw runtime locator evidence') from exc
            need(type(proof.get('count')) is int and proof['count']==1 and all(proof.get(k)==loc.get(k) for k in ['locatorType','locatorValue']),f'{target}: runtime locator/count was changed')
            need(proof.get('controlId',target)==target and proof.get('pageId',item.get('pageId'))==item.get('pageId'),f'{target}: runtime proof belongs to another control/page')
            obj=(loc.get('context') or {}).get('object')
            if obj:
                import json
                value=obj.split('=',1)[-1]
                need(bool(value) and re.search(r'(?<![\w.-])'+re.escape(value)+r'(?![\w.-])',json.dumps(proof,ensure_ascii=False)),f'{target}: unrelated runtime object')
        elif loc.get('evidenceType')=='source':
            source_ref(bundle,loc.get('sourceRef'))
            need(bool(loc.get('reason')),f'{target}: source proof lacks reason')
        else:
            raise HandoffError(f'{target}: unknown evidence type')
        candidates.append(loc)
    need(bool(candidates),f'no confirmed locator for {target}')
    return sorted(candidates,key=lambda l:l.get('stability')=='runtime_only')


def locator(bundle,target,index=0):
    choices=usable_candidates(bundle,target)
    need(type(index) is int and 0<=index<len(choices),'invalid locator choice')
    return choices[index]


def evidenced_locators(bundle):
    """Only exact supplied runtime proof can exempt a locator from heuristic bans."""
    allowed=set()
    for target,item in elements(bundle).items():
        if not item.get('locatorCandidates'):
            continue
        try:
            candidates=usable_candidates(bundle,target)
        except HandoffError:
            continue
        for loc in candidates:
            if loc['evidenceType']=='runtime' and bundle['scenario'].get('executionPrecheckRequired'):
                allowed.add((loc['locatorType'],loc['locatorValue']))
    return allowed


ORACLE_FIELDS=('scenarioId','sourceFunctionCaseIds','title','businessGoal','requiredActions','requiredObservations','expectedResult','preconditions','preconditionRefs','dataNeeds','variables')


def effective_bundle(original, repair=None):
    result=copy.deepcopy(original)
    if not repair:
        return result
    need(repair.get('evidenceNotes'), 'repair requires evidenceNotes')
    before=result['scenario'];after=repair.get('scenario',before)
    for key in ORACLE_FIELDS:
        need(before.get(key)==after.get(key),f'repair changed source oracle: {key}')
    need(not before.get('executionPrecheckRequired') or after.get('executionPrecheckRequired') is True,'repair dropped historical execution precheck')
    need(before.get('dataPlan')==after.get('dataPlan'),'repair cannot manufacture fixture/precondition evidence')
    old_bindings={b['observationIndex']:b for b in before.get('observationBindings',[])}
    for b in after.get('observationBindings',[]):
        old=old_bindings.get(b['observationIndex'])
        need(old is not None and all(old.get(k)==b.get(k) for k in ['functionCaseId','expectationIds']),'repair changed observation/source association')
        if old.get('checks'):
            need(old['checks']==b.get('checks'),'repair changed previously bound oracle checks')
    surface=repair.get('surface',result['surface'])
    need(surface.get('runtimeEvidence')==result['surface'].get('runtimeEvidence'),'repair changed immutable runtime registry')
    need(surface.get('app')==result['surface'].get('app'),'repair changed app context')
    old_elements=elements(result)
    result['surface']=copy.deepcopy(surface)
    for target,item in elements(result).items():
        previous=old_elements.get(target,{})
        if previous:
            for key in ['sourceRef','pageId','containerId','semanticName','controlType','role','route','componentFile']:
                need(item.get(key)==previous.get(key),f'repair reassigned element identity {target}/{key}')
            old_proven=[l for l in previous.get('locatorCandidates',[]) if l.get('confirmed')]
            need(all(l in item.get('locatorCandidates',[]) for l in old_proven),'repair removed existing locator evidence')
            need(all(o in item.get('options',[]) for o in previous.get('options',[]) if o.get('availability')=='addressable'),'repair removed/reassigned a confirmed option')
        for loc in item.get('locatorCandidates',[]):
            if loc.get('confirmed') and loc not in previous.get('locatorCandidates',[]):
                need(loc.get('evidenceType')=='runtime','new source locator remains a candidate until independently confirmed')
                usable_candidates(result,target)
    need(set(old_elements)<=set(elements(result)),'repair removed surface elements')
    frames=repair.get('caseFrameworks',result['caseFrameworks'])
    old_frames={f['functionCaseId']:f for f in result['caseFrameworks']}
    need({f['functionCaseId'] for f in frames}==set(old_frames),'repair changed selected formal cases')
    for frame in frames:
        old=old_frames[frame['functionCaseId']]
        need(all(frame.get(k)==old.get(k) for k in ['caseGoal','coreExpectationIds']),'repair changed primary goal')
        a={e['expectationId']:e for e in old['expectedResults']};b={e['expectationId']:e for e in frame['expectedResults']}
        need(a.keys()==b.keys(),'repair lost an original expectation')
        need(all(all(a[e].get(k)==b[e].get(k) for k in ['sourceStepNos','sourceQuote','text']) for e in a),'repair rewrote a formal expectation')
        bound={e for binding in after.get('observationBindings',[]) if binding['functionCaseId']==frame['functionCaseId'] for e in binding['expectationIds']}
        for eid in a:
            if a[eid].get('disposition')!=b[eid].get('disposition'):
                need(eid in bound and b[eid].get('disposition')=='executable','repair changed an unbound expectation disposition')
    result['caseFrameworks']=copy.deepcopy(frames);result['scenario']=copy.deepcopy(after)
    if 'observationSchedule' in repair:
        if original.get('observationSchedule'):
            need(original['observationSchedule']==repair['observationSchedule'],'repair changed a reviewed observation schedule')
        result['observationSchedule']=copy.deepcopy(repair['observationSchedule'])
    return result


def resolve_value(bundle, text):
    need(isinstance(text,str),'expected value must be text')
    def replace(match):
        name=match[1]
        var=bundle['scenario'].get('variables',{}).get(name)
        need(isinstance(var,dict) and 'value' in var and bool(var.get('source')),f'variable {name} has no supplied fixed value/provenance')
        need(isinstance(var['value'],(str,int,float)) and not isinstance(var['value'],bool),f'variable {name} is not scalar')
        return str(var['value'])
    value=re.sub(r'\{\{([A-Za-z0-9_.]+)\}\}',replace,text)
    need('{{' not in value and bool(value),'unresolved/per-step dynamic oracle value')
    return value


def page_url(bundle,page_id):
    page=elements(bundle).get(page_id,{})
    need('route' in page,f'unknown page route {page_id}')
    route=page['route'];base=bundle['context']['targetBaseUrl'].rstrip('/')
    need(isinstance(route,str) and bool(route),'page has no route')
    return route if route.startswith(('http://','https://')) else base+'/'+route.lstrip('/')


def check_step(bundle, check, timeout=10000):
    target=check['targetId'];op=check['operator']
    if op.startswith('url_'):
        need(op in {'url_eq','url_contains'},f'unsupported observation operator {op}')
        need(target in {p['pageId'] for p in bundle['surface']['pages']},'URL assertion must target a page')
        return {'keyword':'assert_url','operationValue':resolve_value(bundle,check['expectedText']),'comparator':'eq' if op=='url_eq' else 'contains'}
    loc=locator(bundle,target)
    result={'locatorType':loc['locatorType'],'locatorValue':loc['locatorValue']}
    if op=='visible':
        result.update(keyword='assert_visible',operationValue=str(timeout))
    else:
        need(op in {'text_eq','text_contains'},f'unsupported observation operator {op}')
        item=elements(bundle)[target]
        need(item.get('controlType','').lower() not in {'input','textarea','textinput','passwordinput','numberinput'} and item.get('role') not in {'textbox','searchbox'},'DOM text cannot assert input value')
        value=resolve_value(bundle,check['expectedText'])
        refs=check.get('valueRefs',[])
        if item.get('sampleValueRef'):
            refs=list(refs)+['/runtimeEvidence'+item['sampleValueRef']]
        for ref in refs:
            try:raw=pointer(bundle['surface'],ref)
            except (HandoffError,KeyError,IndexError,ValueError,TypeError) as exc:
                raise HandoffError('assertion value evidence reference is invalid') from exc
            need(isinstance(raw,(str,int,float)) and not isinstance(raw,bool),'assertion value evidence must be scalar')
            need(value==str(raw) if op=='text_eq' else value in str(raw),'assertion value differs from its supplied record evidence')
        result.update(keyword='assert_text',operationValue=value,comparator='eq' if op=='text_eq' else 'contains')
    return result


def preflight(bundle):
    context=bundle.get('context',{});base=context.get('targetBaseUrl','');parsed=urlparse(base)
    need(parsed.scheme in {'http','https'} and bool(parsed.netloc),'CLARIFICATION_REQUIRED: 请提供目标环境地址（targetBaseUrl）')
    scenario=bundle['scenario']
    need(scenario.get('status')=='ready' and scenario.get('gapCategory') is None,'SCENARIO_BLOCKED: unresolved scenario status/gap')
    need(scenario.get('uiAssertability')!='non_ui','SCENARIO_BLOCKED: non-UI primary goal')
    need(context.get('authentication',{}).get('mode') in {'suite_setup','inline'},'CLARIFICATION_REQUIRED: 请提供登录准备方式或共享登录套件声明')
    if context['authentication']['mode']=='inline':
        auth=context['authentication']
        need(all(auth.get(k) for k in ['loginPageId','fields','submitControlId','postLoginControlId']),'CLARIFICATION_REQUIRED: 登录需提供页面/字段绑定/提交控件/登录后稳定控件')
        page_url(bundle,auth['loginPageId'])
        for field in auth['fields']:
            usable_candidates(bundle,field['controlId'])
            try:need(pointer(bundle,field['valueRef']) not in [None,''],'missing supplied credential')
            except (HandoffError,KeyError,ValueError,TypeError,IndexError) as exc:raise HandoffError('CLARIFICATION_REQUIRED: 缺少已提供的登录字段值') from exc
        usable_candidates(bundle,auth['submitControlId']);usable_candidates(bundle,auth['postLoginControlId'])
    frames={f['functionCaseId']:f for f in bundle.get('caseFrameworks',[])}
    formal={f['caseId']:f for f in bundle.get('functionalCases',[])}
    ids=scenario['sourceFunctionCaseIds'];expectations={}
    required_pre=set()
    for cid in ids:
        need(cid in frames and cid in formal,f'missing original framework/case {cid}')
        need(bool(frames[cid].get('coreExpectationIds')),'missing business core')
        steps=formal[cid]['content']['steps']
        for expected in frames[cid]['expectedResults']:
            expectations[(cid,expected['expectationId'])]=expected
            numbers=expected.get('sourceStepNos',[])
            need(len(numbers)==1 and type(numbers[0]) is int and 1<=numbers[0]<=len(steps),'invalid original source step')
            need(expected.get('text')==expected.get('sourceQuote') and expected.get('sourceQuote') in steps[numbers[0]-1]['expected'],'source expectation was changed')
        required_pre|={(cid,f'P{i:02}') for i,_ in enumerate(formal[cid]['content'].get('preconditions',[]),1)}
    need({(x['functionCaseId'],x['preconditionId']) for x in scenario.get('preconditionRefs',[])}==required_pre,'original preconditions lost')
    plans={(p['functionCaseId'],p['preconditionId']):p for p in scenario.get('dataPlan',[])}
    need(set(plans)==required_pre,'missing original precondition plan')
    for key,plan in plans.items():
        need(plan.get('status') in {'given_fixture','ui_preparable','bookkeeping'},f'SCENARIO_BLOCKED: prerequisite {key} needs input')
        if plan['status']=='given_fixture':
            refs=plan.get('evidenceRefs',[]);need(bool(refs),'fixture lacks provenance')
            for ref in refs:
                if ref=='taskContext' or ref in elements(bundle):continue
                try:pointer(bundle['surface'],ref)
                except (HandoffError,KeyError,ValueError,TypeError,IndexError) as exc:raise HandoffError('fixture evidence reference is invalid') from exc
        if plan['status']=='ui_preparable':
            need(bool(plan.get('controlIds')),'UI preparation lacks controls')
            for target in plan['controlIds']:usable_candidates(bundle,target)
        if plan['status']=='bookkeeping':
            text=formal[key[0]]['content']['preconditions'][int(key[1][1:])-1]
            need(bool(re.match(r'^(?:\d+[.、)]\s*)?(?:已记录|记录|record)',text,re.I)) and not any(word in text for word in ['并确认','并具备','并保证','且确认','confirm that','ensure that']),'environment/state condition is not pure bookkeeping')
    actions=scenario.get('requiredActions',[])
    bindings=scenario.get('actionBindings',[])
    need(sorted(b['actionIndex'] for b in bindings)==list(range(1,len(actions)+1)),'actions lack exact bindings')
    for binding in bindings:
        need(binding.get('operation') in {'navigate','activate','input','select','observe','wait','sequence'},'unknown action operation')
        for target in binding.get('controlIds',[]):usable_candidates(bundle,target)
        for page in binding.get('pageIds',[]):page_url(bundle,page)
        if binding['operation']=='select':
            need(binding.get('selectedOptions'),'select field is not a confirmed option')
            for selected in binding['selectedOptions']:
                select=elements(bundle).get(selected['controlId'],{})
                need(any(o.get('controlId')==selected.get('optionControlId') and o.get('availability')=='addressable' for o in select.get('options',[])),'option does not belong to select')
                usable_candidates(bundle,selected['optionControlId'])
    observed={cid:set() for cid in ids}
    obs=scenario.get('observationBindings',[])
    need(sorted(b['observationIndex'] for b in obs)==list(range(1,len(scenario['requiredObservations'])+1)),'observations lack exact bindings')
    for binding in obs:
        cid=binding['functionCaseId'];need(cid in ids,'foreign observation case')
        keys=[(cid,e) for e in binding['expectationIds']]
        need(bool(keys) and all(k in expectations and expectations[k]['disposition']=='executable' for k in keys),'observation has no executable original expectation')
        need(scenario['requiredObservations'][binding['observationIndex']-1]=='\n'.join(expectations[k]['text'] for k in keys),'observation changed the oracle')
        observed[cid].update(binding['expectationIds'])
        need(bool(binding.get('checks')),'observation has no concrete checks')
        for check in binding['checks']:check_step(bundle,check)
        schedule=bundle.get('observationSchedule',{}).get(str(binding['observationIndex']),binding)
        need(type(schedule.get('afterActionIndex')) is int and 0<=schedule['afterActionIndex']<=len(actions),'SCENARIO_BLOCKED: missing reviewed observation checkpoint schedule')
        source_numbers=sorted({n for key in keys for n in expectations[key]['sourceStepNos']})
        need(schedule.get('sourceStepNos')==source_numbers,'checkpoint schedule must cite the original source steps')
    for cid in ids:
        need(set(frames[cid]['coreExpectationIds'])<=observed[cid],f'SCENARIO_BLOCKED: incomplete primary core {cid}')


def validate_handoff(cases,bundle,trace):
    preflight(bundle);s=bundle['scenario'];all_elements=elements(bundle)
    need(trace.get('schemaVersion')=='ui_case_trace/1.0' and trace.get('scenarioId')==s['scenarioId'],'trace does not match scenario')
    rows=trace.get('steps',[]);by_step={(r.get('caseOrderNo'),r.get('stepOrderNo')):r for r in rows}
    need(len(by_step)==len(rows),'duplicate trace step')
    actual_keys={(c['orderNo'],st['orderNo']) for c in cases for st in c['stepsJson']}
    need(actual_keys==set(by_step),'trace has missing/phantom YAML steps')
    obs={b['observationIndex']:b for b in s['observationBindings']};actions={b['actionIndex']:b for b in s['actionBindings']}
    expected_checks={(b['observationIndex'],i) for b in obs.values() for i,_ in enumerate(b['checks'],1)}
    covered=set();case_observed={};case_checks={};action_steps={};action_targets={};case_steps={c['orderNo']:{st['orderNo']:st for st in c['stepsJson']} for c in cases}
    operators=bundle.get('capabilities',{}).get('keywords')
    for case in cases:
        no=case['orderNo'];need(case.get('enabled') is True,'generated case is disabled')
        case_observed[no]={cid:set() for cid in s['sourceFunctionCaseIds']}
        case_checks[no]=set()
        for step in case['stepsJson']:
            n=step['orderNo'];row=by_step[(no,n)]
            need(step.get('enabled') is True and step.get('continueOnFailure') is False,'required step disabled or allowed to fail')
            if operators is not None:need(step['keyword'] in operators,'keyword unsupported by supplied executor')
            need('{{' not in str(step.get('operationValue','')),'unresolved/per-step template in a scenario-bound case')
            action=row.get('actionIndex')
            if action is not None:
                need(action in actions,'unknown action reference')
                action_steps.setdefault((no,action),[]).append(n)
            kind=row.get('kind');need(kind in {'action','check','setup'},'unknown trace kind')
            if kind=='check':
                need(bool(row.get('observations')),'check has no observation references')
                for ref in row['observations']:
                    pair=(ref['observationIndex'],ref['checkIndex']);need(pair in expected_checks,'unknown check reference')
                    binding=obs[pair[0]];check=binding['checks'][pair[1]-1];expected=check_step(bundle,check)
                    # A later polling text wait may implement containment, never equality.
                    if step.get('keyword')=='wait_text' and expected.get('keyword')=='assert_text' and expected.get('comparator')=='contains':
                        expected.pop('comparator');expected['keyword']='wait_text'
                    for key in ['keyword','locatorType','locatorValue','operationValue','comparator']:
                        if key=='operationValue' and expected['keyword']=='assert_visible':
                            need(str(step.get(key,'')).isdigit() and int(step[key])>0,'invalid visibility timeout')
                        else:need(step.get(key)==expected.get(key),f'assertion {pair} changes target/operator/value')
                    covered.add(pair);case_checks[no].add(pair);case_observed[no][binding['functionCaseId']].update(binding['expectationIds'])
                    schedule=bundle.get('observationSchedule',{}).get(str(binding['observationIndex']),binding)
                    after=schedule['afterActionIndex'];before=schedule.get('beforeActionIndex')
                    need(row.get('afterActionIndex')==after and row.get('beforeActionIndex')==before,'trace changed reviewed checkpoint schedule')
                    need(type(after) is int and 0<=after<=len(actions),'observation needs an explicit action checkpoint')
                    if after:
                        positions=action_steps.get((no,after),[])
                        need(bool(positions),'observation precedes its required action')
                        need(n>=min(positions) if actions[after]['operation']=='observe' else n>max(positions),'assertion before triggering action')
                    if before is not None:
                        need(type(before) is int and after<before<=len(actions),'invalid beforeActionIndex')
                    if action is not None:
                        need(actions[action]['operation']=='observe','assertion cannot substitute for an explicit operation')
                        action_targets.setdefault((no,action),set()).add(check['targetId'])
            else:
                target=row.get('targetId');page=row.get('pageId');kw=step['keyword']
                if kw=='open':
                    need(page in all_elements,'open lacks page evidence')
                    need(step.get('operationValue')==page_url(bundle,page),'open differs from declared page/base URL')
                    used=page
                else:
                    need(target in all_elements,'operation/setup lacks target evidence')
                    choices=usable_candidates(bundle,target)
                    need(any(step.get('locatorType')==l['locatorType'] and step.get('locatorValue')==l['locatorValue'] for l in choices),'operation locator differs from proven target')
                    used=target
                if kind=='action':
                    need(action is not None,'operation lacks source action')
                    b=actions[action];allowed=set(b.get('controlIds',[])+b.get('pageIds',[]))
                    allowed|={x['optionControlId'] for x in b.get('selectedOptions',[])}
                    need(used in allowed,'operation belongs to another object/action')
                    allowed_kw={'navigate':{'open','click'},'activate':{'click','dblclick'},'input':{'input'},'select':{'click'},'wait':{'wait_text','assert_visible'},'sequence':{'open','click','input','press'},'observe':set()}
                    need(kw in allowed_kw[b['operation']],'action operation was weakened/replaced')
                    action_targets.setdefault((no,action),set()).add(used)
                else:
                    need(row.get('purpose') in {'login','precondition','navigation_wait'},'unjustified setup step')
                    if row['purpose']=='login':need(bundle['context']['authentication']['mode']=='inline','extra login outside declared setup')
                    if row['purpose']=='navigation_wait':need(kw=='assert_visible','navigation_wait requires a polling visible element')
                    if row['purpose']=='precondition':
                        plan=next((p for p in s['dataPlan'] if p['functionCaseId']==row.get('functionCaseId') and p['preconditionId']==row.get('preconditionId')),None)
                        need(plan and plan['status']=='ui_preparable' and target in plan.get('controlIds',[]),'setup does not implement a declared preparation')
                if kw=='input':
                    try:value=pointer(bundle,row.get('valueRef'))
                    except (HandoffError,ValueError,KeyError,TypeError,IndexError) as exc:raise HandoffError('input lacks supplied valueRef') from exc
                    need(str(value)==step.get('operationValue'),'input value was invented')
                if kw=='press':need(step.get('operationValue') in {'Enter','Escape','Tab','Shift+Tab','Control+A','Meta+A'},'unsupported/unprovided key')
    need(covered==expected_checks,'required observation/check dropped')
    frames={f['functionCaseId']:f for f in bundle['caseFrameworks']}
    for case in cases:
        no=case['orderNo']
        need(case_checks[no]==expected_checks,'required checks were split across cases')
        for cid in s['sourceFunctionCaseIds']:
            need(set(frames[cid]['coreExpectationIds'])<=case_observed[no][cid],'core was split across unrelated cases')
        previous=0
        for index,b in actions.items():
            positions=action_steps.get((no,index),[])
            need(bool(positions) and min(positions)>=previous,'required action missing/out of order')
            previous=max(positions)
            required=set(b.get('controlIds',[])+b.get('pageIds',[]))
            required|={x['optionControlId'] for x in b.get('selectedOptions',[])}
            need(required<=action_targets.get((no,index),set()),'explicit page/control/option action was omitted')
            for selected in b.get('selectedOptions',[]):
                parent=[n for n in positions if by_step[(no,n)].get('targetId')==selected['controlId']]
                option=[n for n in positions if by_step[(no,n)].get('targetId')==selected['optionControlId']]
                need(bool(parent) and bool(option) and min(option)>min(parent),'selected option must follow opening its parent field')
        for n,step in case_steps[no].items():
            row=by_step[(no,n)]
            if row['kind']=='check':
                for ref in row['observations']:
                    binding=obs[ref['observationIndex']];schedule=bundle.get('observationSchedule',{}).get(str(binding['observationIndex']),binding);before=schedule.get('beforeActionIndex')
                    after=schedule['afterActionIndex']
                    if after and actions[after]['operation']!='observe':
                        need(n>max(action_steps[(no,after)]),'checkpoint precedes the end of its triggering action')
                    if before:
                        need(n<min(action_steps[(no,before)]),'before/after observations collapsed to one final check')
            if step['keyword']=='assert_url':
                navigations=[j for j in range(1,n) if case_steps[no][j]['keyword'] in {'open','click','dblclick','reload'}]
                need(bool(navigations),'URL assertion lacks navigation')
                last=navigations[-1]
                need(case_steps[no][last]['keyword']=='open' or any(case_steps[no][j]['keyword'] in {'assert_visible','wait_text'} for j in range(last+1,n)),'URL asserted after click without a polling wait')
    if bundle['context']['authentication']['mode']=='inline':
        auth=bundle['context']['authentication']
        for case in cases:
            rows_for_case=[r for r in rows if r['caseOrderNo']==case['orderNo'] and r.get('purpose')=='login']
            steps=case_steps[case['orderNo']]
            opened=[r['stepOrderNo'] for r in rows_for_case if steps[r['stepOrderNo']]['keyword']=='open' and r.get('pageId')==auth['loginPageId']]
            need(bool(opened),'inline login lacks its declared page')
            inputs=[]
            for field in auth['fields']:
                matches=[r['stepOrderNo'] for r in rows_for_case if steps[r['stepOrderNo']]['keyword']=='input' and r.get('targetId')==field['controlId'] and r.get('valueRef')==field['valueRef']]
                need(bool(matches) and min(matches)>min(opened),'inline login lacks a declared credential field')
                inputs.extend(matches)
            submits=[r['stepOrderNo'] for r in rows_for_case if steps[r['stepOrderNo']]['keyword']=='click' and r.get('targetId')==auth['submitControlId']]
            need(bool(submits) and min(submits)>max(inputs),'inline login lacks ordered submission')
            waits=[r['stepOrderNo'] for r in rows_for_case if steps[r['stepOrderNo']]['keyword']=='assert_visible' and r.get('targetId')==auth['postLoginControlId']]
            need(bool(waits) and min(waits)>min(submits),'inline login lacks post-login stable polling wait')
            first_action=min(n for (no,_),positions in action_steps.items() if no==case['orderNo'] for n in positions)
            need(first_action>min(waits),'business flow started before login completed')
    for plan in s['dataPlan']:
        if plan['status']=='ui_preparable':
            auth=bundle['context']['authentication']
            delegated=any(p.get('functionCaseId')==plan['functionCaseId'] and p.get('preconditionId')==plan['preconditionId'] for p in auth.get('preparedPreconditions',[]))
            if delegated:
                need(auth['mode']=='suite_setup' and auth.get('loginPageId'),'shared preparation requires an explicit login page')
                need(all(all_elements[t].get('pageId')==auth['loginPageId'] for t in plan['controlIds']),'shared login cannot satisfy unrelated data preparation')
                continue
            for case in cases:
                preparation_rows=[r for r in rows if r['caseOrderNo']==case['orderNo'] and r.get('purpose')=='precondition' and r.get('functionCaseId')==plan['functionCaseId'] and r.get('preconditionId')==plan['preconditionId']]
                prepared={r.get('targetId') for r in preparation_rows}
                first_action=min(n for (no,_),positions in action_steps.items() if no==case['orderNo'] for n in positions)
                need(all(r['stepOrderNo']<first_action for r in preparation_rows),'UI preparation occurred after the business flow started')
                if auth['mode']=='inline' and all(all_elements[t].get('pageId')==auth['loginPageId'] for t in plan['controlIds']):
                    prepared|={r.get('targetId') for r in rows if r['caseOrderNo']==case['orderNo'] and r.get('purpose')=='login'}
                need(set(plan['controlIds'])<=prepared,'declared UI preparation was not emitted')
    need(not s.get('executionPrecheckRequired') or trace.get('executionPrecheckRequired') is True,'historical fixture precheck was dropped')
