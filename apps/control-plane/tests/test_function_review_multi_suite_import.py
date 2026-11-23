from support.openapi_schema import openapi_schema


def test_function_candidate_edit_and_confirmed_import_routes_are_public():
    paths = openapi_schema()["paths"]

    assert (
        "put"
        in paths[
            "/v1/requirements/{requirementId}/generation/{kind}/stages/{stage}/candidates/{candidateId}"
        ]
    )
    assert (
        "post"
        in paths["/v1/requirements/{requirementId}/generation/{kind}/stages/{stage}/current/import"]
    )
