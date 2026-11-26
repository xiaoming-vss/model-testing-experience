"""Historical use case verification and frozen batch handoff contract."""

from typing import Any

from .historical_requirement_artifacts import parse_historical_json, validate_historical_json

VERIFICATION_BATCH_INPUT = "historical_test_case_verification_input"
VERIFICATION_RUN_INPUT = "historical_test_case_verification_run_input"
VERIFICATION_RUN_RESULT = "historical_test_case_verification_result"
IDENTITY_FIELDS = ("requirementId", "materialSnapshotId", "impactResultId")
EVIDENCE_FIELDS = {"precondition": "preconditions", "step": "steps"}


def verification_run_header(artifact_type: str, source: dict[str, Any]) -> dict[str, Any]:
    """Keep run identity and artifact version synchronized across producer and consumer."""
    return {
        "schemaVersion": "0.1",
        "artifactType": artifact_type,
        **{key: source[key] for key in IDENTITY_FIELDS},
    }


def _run_document(value: object, artifact_type: str, *fields: str) -> dict[str, Any]:
    value = parse_historical_json(value)
    required = {"schemaVersion", "artifactType", "batches", *IDENTITY_FIELDS, *fields}
    if not isinstance(value, dict) or set(value) != required:
        raise ValueError("历史用例核验运行结构无效")
    if (
        value["schemaVersion"] != "0.1"
        or value["artifactType"] != artifact_type
        or not isinstance(value["batches"], list)
        or any(not isinstance(value[key], str) or not value[key] for key in IDENTITY_FIELDS)
    ):
        raise ValueError("历史用例核验运行身份或批次无效")
    return value


def _positions(case: dict[str, Any], field: str) -> dict[int, dict[str, Any]]:
    entries = case[field]
    positions = {entry["position"]: entry for entry in entries}
    if len(positions) != len(entries):
        raise ValueError("历史用例证据位置重复")
    if case["contentScope"] == "full_case" and set(positions) != set(range(1, len(entries) + 1)):
        raise ValueError("历史用例完整快照缺少证据位置")
    return positions


def _validate_excerpt(case: dict[str, Any], full: dict[str, Any]) -> None:
    for field in ("caseId", "caseSnapshotId", "requirementId", "suiteId", "module", "title"):
        if case[field] != full[field]:
            raise ValueError("历史用例片段与完整快照的身份不一致")
    if case["contentScope"] != "matched_excerpt" or full["contentScope"] != "full_case":
        raise ValueError("历史用例片段或完整快照标记无效")
    for field in EVIDENCE_FIELDS.values():
        original = _positions(full, field)
        if any(
            original.get(position) != item for position, item in _positions(case, field).items()
        ):
            raise ValueError("历史用例片段与冻结完整快照不一致")


def validate_verification_run_input(value: object) -> dict[str, Any]:
    source = _run_document(value, VERIFICATION_RUN_INPUT, "fullCases")
    full_cases = source["fullCases"]
    if not isinstance(full_cases, dict):
        raise ValueError("历史用例完整快照结构无效")
    batch_ids: set[str] = set()
    selected: set[str] = set()
    seen: set[tuple[str, str]] = set()
    for batch in source["batches"]:
        batch = validate_historical_json(batch, "historical-test-case-verification-input")
        if any(batch[key] != source[key] for key in IDENTITY_FIELDS):
            raise ValueError("历史用例核验输入批次属于其他运行")
        if batch["batchId"] in batch_ids:
            raise ValueError("历史用例核验输入批次重复")
        batch_ids.add(batch["batchId"])
        originals = []
        for case in batch["candidateCases"]:
            case_id = case["caseId"]
            key = (batch["impact"]["impactId"], case_id)
            if key in seen or case_id not in full_cases:
                raise ValueError("规则影响项中的候选重复或缺少完整快照")
            seen.add(key)
            selected.add(case_id)
            originals.append(full_cases[case_id])
        validate_historical_json(
            {**batch, "candidateCases": originals}, "historical-test-case-verification-input"
        )
        for case, full in zip(batch["candidateCases"], originals, strict=True):
            _validate_excerpt(case, full)
    if selected != set(full_cases):
        raise ValueError("历史用例完整快照包含无关联用例")
    return source


def validate_verification_batch_output(value: object, batch: dict[str, Any]) -> dict[str, Any]:
    result = validate_historical_json(value, "historical-test-case-verification-output")
    if (
        any(result[key] != batch[key] for key in (*IDENTITY_FIELDS, "batchId"))
        or result["impactId"] != batch["impact"]["impactId"]
    ):
        raise ValueError("历史用例核验输出批次身份无效")
    findings = {item["caseId"]: item for item in result["caseFindings"]}
    cases = {item["caseId"]: item for item in batch["candidateCases"]}
    if len(findings) != len(result["caseFindings"]) or findings.keys() != cases.keys():
        raise ValueError("历史用例核验结果缺失、重复或包含其他用例")
    field, id_field = (
        ("supplementalPoints", "pointId")
        if result["schemaVersion"] == "0.2"
        else ("supplementalScenarios", "scenarioId")
    )
    points = result[field]
    if len({item[id_field] for item in points}) != len(points):
        raise ValueError("历史用例核验补测标识重复")
    for case_id, finding in findings.items():
        case = cases[case_id]
        if finding["caseSnapshotId"] != case["caseSnapshotId"]:
            raise ValueError("历史用例核验引用了其他用例快照")
        evidence = {kind: _positions(case, field) for kind, field in EVIDENCE_FIELDS.items()}
        for item in finding["evidence"]:
            if item["position"] not in evidence[item["kind"]]:
                raise ValueError("历史用例核验引用了不存在的证据位置")
        full = case["contentScope"] == "full_case"
        if (finding["decision"] == "invalidate" and not full) or (
            finding["needsFullCase"] and full
        ):
            raise ValueError("历史用例核验的失效或补读结论缺少合法输入")
    return result


def full_case_batch(
    source: dict[str, Any], batch: dict[str, Any], first_pass: dict[str, Any]
) -> dict[str, Any] | None:
    """Build the one permitted follow-up from cases actually requested by a validated pass."""
    originals = [
        source["fullCases"][finding["caseId"]]
        for finding in first_pass["caseFindings"]
        if finding["needsFullCase"]
    ]
    return {**batch, "candidateCases": originals} if originals else None


def validate_verification_run_output(value: object, frozen: object) -> dict[str, Any]:
    source = validate_verification_run_input(frozen)
    result = _run_document(value, VERIFICATION_RUN_RESULT)
    if any(result[key] != source[key] for key in IDENTITY_FIELDS) or len(result["batches"]) != len(
        source["batches"]
    ):
        raise ValueError("历史用例核验结果与运行快照或批次数不一致")
    for item, batch in zip(result["batches"], source["batches"], strict=True):
        if not isinstance(item, dict) or set(item) != {"firstPass", "fullCasePass"}:
            raise ValueError("历史用例核验的批次回传结构无效")
        first_pass = validate_verification_batch_output(item["firstPass"], batch)
        follow_up = full_case_batch(source, batch, first_pass)
        if follow_up is not None:
            validate_verification_batch_output(item["fullCasePass"], follow_up)
        elif item["fullCasePass"] is not None:
            raise ValueError("历史用例核验回传了未请求的补读结果")
    return result
