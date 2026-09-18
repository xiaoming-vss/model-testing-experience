from testing_agent.app import create_app


def tags_for(path: str, method: str) -> list[str]:
    operation = create_app().openapi()["paths"][path][method.lower()]
    return operation["tags"]


def test_v1_routes_are_grouped_in_openapi():
    assert tags_for("/v1/login", "post") == ["Auth"]
    assert tags_for("/v1/projects", "get") == ["Projects"]
    assert tags_for("/v1/api-collections/{collectionId}", "get") == ["API Tests"]
    assert tags_for("/v1/function-test-suites/{suiteId}", "get") == ["Function Tests"]
    assert tags_for("/v1/ui-test-suites/{suiteId}", "get") == ["UI Tests"]
    assert tags_for("/v1/api-case-generate-tasks/{taskId}", "get") == ["API AI Tasks"]
    assert tags_for("/v1/function-case-generate-tasks/{taskId}", "get") == ["Function AI Tasks"]
    assert tags_for("/v1/test-report-generate-runs/{runId}", "get") == ["Test Report AI Tasks"]
    assert tags_for("/v1/test-report-generate-runs/{runId}/pdf", "get") == ["Test Report AI Tasks"]
    assert tags_for("/v1/api-case-runs/{runId}", "get") == ["API Runs"]
    assert tags_for("/v1/ui-test-case-runs/{runId}", "get") == ["UI Runs"]
    assert tags_for("/v1/integrations/zentao/connections", "get") == ["Zentao Integrations"]
    assert tags_for("/v1/integrations/llm/connections", "get") == ["LLM Integrations"]


def test_internal_worker_routes_are_grouped_in_openapi():
    assert tags_for("/internal/ui-worker/tasks/claim", "post") == ["Internal UI Worker"]
    assert tags_for("/internal/api-worker/tasks/claim", "post") == ["Internal API Worker"]
    assert tags_for("/internal/ai-worker/tasks/claim", "post") == ["Internal AI Worker"]


def test_json_success_responses_have_go_style_schema():
    schema = create_app().openapi()
    offenders: list[str] = []

    def resolve_ref(node: dict) -> dict:
        ref = node.get("$ref")
        if not ref:
            return node
        _, _, name = ref.rpartition("/")
        return schema["components"]["schemas"][name]

    for path, path_item in schema["paths"].items():
        if path.startswith("/internal/"):
            continue
        for method, operation in path_item.items():
            if not isinstance(operation, dict):
                continue
            content = (
                operation.get("responses", {})
                .get("200", {})
                .get("content", {})
                .get("application/json")
            )
            if content is None:
                continue
            response_schema = content.get("schema")
            if response_schema == {}:
                offenders.append(f"{method.upper()} {path}")
                continue
            properties = resolve_ref(response_schema).get("properties", {})
            if {"code", "message", "data"} - set(properties):
                offenders.append(f"{method.upper()} {path}")

    assert offenders == []


def test_core_success_response_data_uses_declared_models():
    schema = create_app().openapi()

    def resolve_ref(node: dict) -> dict:
        ref = node.get("$ref")
        if not ref:
            return node
        _, _, name = ref.rpartition("/")
        return schema["components"]["schemas"][name]

    project_list_schema = schema["paths"]["/v1/projects"]["get"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"]
    project_detail_schema = schema["paths"]["/v1/projects/{projectId}"]["get"]["responses"]["200"][
        "content"
    ]["application/json"]["schema"]

    list_data_schema = resolve_ref(project_list_schema)["properties"]["data"]
    detail_data_schema = resolve_ref(project_detail_schema)["properties"]["data"]

    list_data_schema = resolve_ref(list_data_schema)
    assert list_data_schema["properties"]["total"]["type"] == "integer"
    assert list_data_schema["properties"]["items"]["items"] == {
        "$ref": "#/components/schemas/ProjectResponse"
    }
    assert detail_data_schema == {"$ref": "#/components/schemas/ProjectResponse"}


def test_openapi_does_not_emit_additional_properties_placeholders():
    schema = create_app().openapi()
    offenders: list[str] = []

    def walk(node: object, path: str) -> None:
        if isinstance(node, dict):
            if node.get("additionalProperties") is True:
                offenders.append(path)
            for key, value in node.items():
                walk(value, f"{path}/{key}")
        elif isinstance(node, list):
            for index, value in enumerate(node):
                walk(value, f"{path}/{index}")

    walk(schema, "#")

    assert offenders == []


def test_requirement_analysis_run_request_exposes_checkpoint_protocol_fields():
    schema = create_app().openapi()
    request_schema = schema["paths"]["/v1/requirement-analysis-tasks/{taskId}/run"]["post"][
        "requestBody"
    ]["content"]["application/json"]["schema"]
    _, _, schema_name = request_schema["$ref"].rpartition("/")
    properties = schema["components"]["schemas"][schema_name]["properties"]

    assert "connectionId" in properties
    assert "instruction" in properties
    assert "checkpointEnabled" in properties
    assert "configJson" in properties


def test_requirement_response_does_not_expose_document_file_metadata_noise():
    schema = create_app().openapi()
    properties = schema["components"]["schemas"]["RequirementResponse"]["properties"]

    assert "documentContentType" not in properties
    assert "documentSize" not in properties
    assert "description" not in properties
    assert "status" not in properties


def test_requirement_requests_do_not_expose_description_or_status():
    schema = create_app().openapi()
    create_properties = schema["components"]["schemas"]["CreateRequirementRequest"]["properties"]
    update_properties = schema["components"]["schemas"]["UpdateRequirementRequest"]["properties"]

    assert "description" not in create_properties
    assert "status" not in create_properties
    assert "description" not in update_properties
    assert "status" not in update_properties
