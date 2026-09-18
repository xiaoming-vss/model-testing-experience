from __future__ import annotations

from fastapi import APIRouter, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse

from testing_agent.core.config import Settings, get_settings
from testing_agent.core.errors import (
    AppError,
    ErrBadRequest,
    ErrInternalServerError,
    ErrUnauthorized,
    app_error_payload,
    success_payload,
    validation_error_detail,
)
from testing_agent.routers.ai_worker import router as ai_worker_router
from testing_agent.routers.api_ai_tasks import router as api_ai_tasks_router
from testing_agent.routers.api_case import router as api_case_router
from testing_agent.routers.api_runs import router as api_runs_router
from testing_agent.routers.api_tests import router as api_tests_router
from testing_agent.routers.api_worker import router as api_worker_router
from testing_agent.routers.auth import router as auth_router
from testing_agent.routers.code_risk_analysis_tasks import router as code_risk_analysis_tasks_router
from testing_agent.routers.function_ai_tasks import router as function_ai_tasks_router
from testing_agent.routers.function_tests import router as function_tests_router
from testing_agent.routers.gitlab_integrations import router as gitlab_integrations_router
from testing_agent.routers.llm_integrations import router as llm_integrations_router
from testing_agent.routers.project_skills import router as project_skills_router
from testing_agent.routers.projects import router as projects_router
from testing_agent.routers.requirement_analysis_runs import (
    router as requirement_analysis_runs_router,
)
from testing_agent.routers.requirements import router as requirements_router
from testing_agent.routers.resource_bindings import router as resource_bindings_router
from testing_agent.routers.shared_services import router as shared_services_router
from testing_agent.routers.sprint_code_overview import router as sprint_code_overview_router
from testing_agent.routers.sprint_metrics import router as sprint_metrics_router
from testing_agent.routers.sprints import router as sprints_router
from testing_agent.routers.test_report_ai_tasks import router as test_report_ai_tasks_router
from testing_agent.routers.ui_ai_tasks import router as ui_ai_tasks_router
from testing_agent.routers.ui_runs import router as ui_runs_router
from testing_agent.routers.ui_tests import router as ui_tests_router
from testing_agent.routers.ui_worker import router as ui_worker_router
from testing_agent.routers.zentao_integrations import router as zentao_integrations_router
from testing_agent.schemas.common import ApiResponse, MessageData, StatusData, UrlData
from testing_agent.services.worker_lease_monitor import lifespan


def _snake_to_camel(value: str) -> str:
    head, *tail = value.split("_")
    return head + "".join(part[:1].upper() + part[1:] for part in tail)


def _go_contract_path(path: str) -> str:
    parts = path.split("{")
    if len(parts) == 1:
        return path
    result = [parts[0]]
    for part in parts[1:]:
        name, rest = part.split("}", 1)
        result.append("{" + _snake_to_camel(name) + "}" + rest)
    return "".join(result)


def _install_go_contract_openapi(app: FastAPI) -> None:
    def custom_openapi() -> dict:
        if app.openapi_schema:
            return app.openapi_schema
        schema = get_openapi(title=app.title, version=app.version, routes=app.routes)
        paths = {}
        for path, path_item in schema.get("paths", {}).items():
            contract_path = _go_contract_path(path)
            for operation in path_item.values():
                if not isinstance(operation, dict):
                    continue
                for param in operation.get("parameters", []):
                    if param.get("in") == "path" and isinstance(param.get("name"), str):
                        param["name"] = _snake_to_camel(param["name"])
            paths[contract_path] = path_item
        schema["paths"] = paths
        app.openapi_schema = schema
        return schema

    # FastAPI supports replacing this method to customize its generated schema.
    app.openapi = custom_openapi  # type: ignore[method-assign]


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(title="testing-agent API", version="1.0.0", lifespan=lifespan)
    app.state.settings = settings

    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        if request.url.path.startswith("/internal/") and exc == ErrUnauthorized:
            return JSONResponse(status_code=401, content={"message": ErrUnauthorized.message})
        return JSONResponse(status_code=exc.http_code, content=app_error_payload(exc, exc.data))

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        error = AppError(
            ErrBadRequest.code, validation_error_detail(list(exc.errors())), ErrBadRequest.http_code
        )
        return JSONResponse(status_code=error.http_code, content=app_error_payload(error))

    @app.exception_handler(Exception)
    async def handle_unexpected_error(_: Request, __: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=ErrInternalServerError.http_code,
            content=app_error_payload(ErrInternalServerError),
        )

    @app.get("/", response_model=ApiResponse[MessageData])
    async def root():
        return success_payload({"message": "testing-agent server is running"})

    @app.get("/swagger/index.html", response_model=ApiResponse[UrlData])
    async def swagger_compat():
        return success_payload({"url": "/docs"})

    v1 = APIRouter(prefix="/v1")

    @v1.get("/health", response_model=ApiResponse[StatusData])
    async def health():
        return success_payload({"status": "ok"})

    v1.include_router(auth_router, tags=["Auth"])
    v1.include_router(projects_router, tags=["Projects"])
    v1.include_router(sprints_router, tags=["Sprints"])
    v1.include_router(requirements_router, tags=["Requirements"])
    v1.include_router(function_tests_router, tags=["Function Tests"])
    v1.include_router(api_tests_router, tags=["API Tests"])
    v1.include_router(api_case_router, tags=["API Tests"])
    v1.include_router(ui_tests_router, tags=["UI Tests"])
    v1.include_router(ui_ai_tasks_router, tags=["UI AI Tasks"])
    v1.include_router(zentao_integrations_router, tags=["Zentao Integrations"])
    v1.include_router(gitlab_integrations_router, tags=["GitLab Integrations"])
    v1.include_router(llm_integrations_router, tags=["LLM Integrations"])
    v1.include_router(shared_services_router, tags=["Shared Services"])
    v1.include_router(resource_bindings_router, tags=["Resource Bindings"])
    v1.include_router(project_skills_router, tags=["Project Skills"])
    v1.include_router(sprint_metrics_router, tags=["Sprint Metrics"])
    v1.include_router(sprint_code_overview_router, tags=["Sprint Metrics"])
    v1.include_router(api_ai_tasks_router, tags=["API AI Tasks"])
    v1.include_router(function_ai_tasks_router, tags=["Function AI Tasks"])
    v1.include_router(requirement_analysis_runs_router, tags=["Requirement Analysis Tasks"])
    v1.include_router(code_risk_analysis_tasks_router, tags=["Code Risk Analysis Tasks"])
    v1.include_router(test_report_ai_tasks_router, tags=["Test Report AI Tasks"])
    v1.include_router(api_runs_router, tags=["API Runs"])
    v1.include_router(ui_runs_router, tags=["UI Runs"])
    app.include_router(v1)

    internal = APIRouter(prefix="/internal")
    internal.include_router(ui_worker_router, tags=["Internal UI Worker"])
    internal.include_router(api_worker_router, tags=["Internal API Worker"])
    internal.include_router(ai_worker_router, tags=["Internal AI Worker"])
    app.include_router(internal)

    _install_go_contract_openapi(app)
    return app


app = create_app()
