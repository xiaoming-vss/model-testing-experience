import ast
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_context_resources_are_split_by_business_resource():
    expected_files = (
        ("routers", "projects.py"),
        ("routers", "sprints.py"),
        ("routers", "requirements.py"),
        ("services", "project.py"),
        ("services", "sprint.py"),
        ("services", "requirement.py"),
    )

    for directory, filename in expected_files:
        assert (PROJECT_ROOT / "src" / "testing_agent" / directory / filename).exists(), (
            f"{directory}/{filename} is missing"
        )


def test_test_assets_are_split_by_testing_domain():
    expected_files = (
        ("routers", "function_tests.py"),
        ("routers", "api_tests.py"),
        ("routers", "ui_tests.py"),
    )

    for directory, filename in expected_files:
        assert (PROJECT_ROOT / "src" / "testing_agent" / directory / filename).exists(), (
            f"{directory}/{filename} is missing"
        )


def test_api_case_uses_go_style_layering():
    expected_files = (
        ("routers", "api_case.py"),
        ("handlers", "api_case.py"),
        ("services", "api_case.py"),
        ("repositories", "api_case.py"),
    )

    for directory, filename in expected_files:
        assert (PROJECT_ROOT / "src" / "testing_agent" / directory / filename).exists(), (
            f"{directory}/{filename} is missing"
        )

    router_source = (PROJECT_ROOT / "src" / "testing_agent" / "routers" / "api_case.py").read_text(
        encoding="utf-8"
    )
    assert "testing_agent.handlers.api_case" in router_source
    assert "testing_agent.routers.assets" not in router_source
    assert "testing_agent.routers.runs" not in router_source


def test_api_resources_do_not_use_legacy_asset_handlers():
    resources = (
        "api_collection",
        "api_environment",
        "api_environment_var",
        "api_assert_rule",
        "api_extract_rule",
    )

    for resource in resources:
        for directory in ("handlers", "services", "repositories"):
            assert (
                PROJECT_ROOT / "src" / "testing_agent" / directory / f"{resource}.py"
            ).exists(), f"{directory}/{resource}.py is missing"

        handler_source = (
            PROJECT_ROOT / "src" / "testing_agent" / "handlers" / f"{resource}.py"
        ).read_text(encoding="utf-8")
        assert "assets_legacy" not in handler_source


def test_function_and_ui_resources_do_not_use_legacy_asset_handlers():
    resources = (
        "function_test_suite",
        "function_test_case",
        "ui_test_suite",
        "ui_test_case",
    )

    for resource in resources:
        for directory in ("handlers", "services", "repositories"):
            assert (
                PROJECT_ROOT / "src" / "testing_agent" / directory / f"{resource}.py"
            ).exists(), f"{directory}/{resource}.py is missing"

        handler_source = (
            PROJECT_ROOT / "src" / "testing_agent" / "handlers" / f"{resource}.py"
        ).read_text(encoding="utf-8")
        assert "assets_legacy" not in handler_source


def test_remaining_routes_are_split_by_business_resource():
    expected_router_files = (
        "zentao_integrations.py",
        "llm_integrations.py",
        "resource_bindings.py",
        "project_skills.py",
        "sprint_metrics.py",
        "api_ai_tasks.py",
        "function_ai_tasks.py",
        "api_runs.py",
        "ui_runs.py",
        "api_worker.py",
        "ui_worker.py",
        "ai_worker.py",
    )

    for filename in expected_router_files:
        assert (PROJECT_ROOT / "src" / "testing_agent" / "routers" / filename).exists(), (
            f"routers/{filename} is missing"
        )


def test_split_routers_do_not_forward_aggregate_routes():
    router_dir = PROJECT_ROOT / "src" / "testing_agent" / "routers"
    split_router_files = (
        "function_tests.py",
        "api_tests.py",
        "ui_tests.py",
        "zentao_integrations.py",
        "llm_integrations.py",
        "resource_bindings.py",
        "project_skills.py",
        "sprint_metrics.py",
        "api_ai_tasks.py",
        "function_ai_tasks.py",
        "api_runs.py",
        "ui_runs.py",
        "api_worker.py",
        "ui_worker.py",
        "ai_worker.py",
    )
    forbidden = (
        "for route in",
        ".routes.append(",
        "router = build_worker_router(",
        "router as assets_router",
        "router as integrations_router",
        "router as project_ops_router",
        "router as ai_tasks_router",
        "router as runs_router",
        "testing_agent.routers.worker",
    )

    for router_name in split_router_files:
        source = (router_dir / router_name).read_text(encoding="utf-8")
        for pattern in forbidden:
            assert pattern not in source, f"{router_name} still forwards routes with {pattern}"


def test_app_does_not_include_aggregate_routers_directly():
    source = (PROJECT_ROOT / "src" / "testing_agent" / "app.py").read_text(encoding="utf-8")

    forbidden_imports = (
        "from testing_agent.routers.integrations import router as integrations_router",
        "from testing_agent.routers.project_ops import router as project_ops_router",
        "from testing_agent.routers.ai_tasks import router as ai_tasks_router",
        "from testing_agent.routers.runs import router as runs_router",
        "from testing_agent.routers.worker import build_worker_router",
    )
    for forbidden in forbidden_imports:
        assert forbidden not in source


def test_migrated_routers_do_not_import_persistence_details():
    forbidden = (
        "from sqlalchemy",
        "import sqlalchemy",
        "from testing_agent.models",
        "from testing_agent.db.session",
    )

    for router_name in ("auth.py", "projects.py", "sprints.py", "requirements.py"):
        source = (PROJECT_ROOT / "src" / "testing_agent" / "routers" / router_name).read_text(
            encoding="utf-8"
        )
        for pattern in forbidden:
            assert pattern not in source, f"{router_name} still imports {pattern}"


def test_routers_do_not_import_persistence_details():
    forbidden = (
        "from sqlalchemy",
        "import sqlalchemy",
        "from testing_agent.models",
        "from testing_agent.db.session",
    )

    for path in (PROJECT_ROOT / "src" / "testing_agent" / "routers").glob("*.py"):
        source = path.read_text(encoding="utf-8")
        for pattern in forbidden:
            assert pattern not in source, f"{path.name} still imports {pattern}"


def test_handlers_do_not_import_persistence_details():
    handlers_dir = PROJECT_ROOT / "src" / "testing_agent" / "handlers"
    assert handlers_dir.exists(), "handlers package is missing"

    forbidden = (
        "from sqlalchemy",
        "import sqlalchemy",
        "from testing_agent.models",
        "from testing_agent.db.session",
    )

    for path in handlers_dir.glob("*.py"):
        source = path.read_text(encoding="utf-8")
        for pattern in forbidden:
            assert pattern not in source, f"{path.name} still imports {pattern}"


def test_no_legacy_service_shims_remain():
    service_dir = PROJECT_ROOT / "src" / "testing_agent" / "services"
    assert not list(service_dir.glob("*_legacy.py"))

    for path in (PROJECT_ROOT / "src" / "testing_agent").rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        for node in ast.walk(ast.parse(source)):
            modules = (
                [node.module or ""]
                if isinstance(node, ast.ImportFrom)
                else [alias.name for alias in node.names]
                if isinstance(node, ast.Import)
                else []
            )
            for module in modules:
                assert not any(part.endswith("_legacy") for part in module.split(".")), (
                    f"{path.name} still imports a legacy module: {module}"
                )


def test_models_are_split_by_business_resource():
    expected_model_files = (
        "api_assert_rule.py",
        "api_case.py",
        "api_case_run.py",
        "api_collection.py",
        "api_collection_run.py",
        "api_environment.py",
        "api_environment_var.py",
        "api_extract_rule.py",
        "ai_generate_task.py",
        "function_test_case.py",
        "function_test_suite.py",
        "integration_connection.py",
        "project.py",
        "project_skill_space.py",
        "requirement.py",
        "resource_binding.py",
        "sprint.py",
        "sprint_daily_metrics.py",
        "ui_test_case.py",
        "ui_test_case_run.py",
        "ui_test_suite.py",
        "ui_test_suite_run.py",
        "user.py",
        "worker_task.py",
    )
    model_dir = PROJECT_ROOT / "src" / "testing_agent" / "models"

    for filename in expected_model_files:
        assert (model_dir / filename).exists(), f"models/{filename} is missing"

    assert not (model_dir / "entities.py").exists()


def test_schemas_are_split_by_business_resource():
    expected_schema_files = (
        "api_assert_rule.py",
        "api_case.py",
        "api_collection.py",
        "api_environment.py",
        "api_environment_var.py",
        "api_extract_rule.py",
        "api_run.py",
        "function_test_case.py",
        "function_test_suite.py",
        "project.py",
        "requirement.py",
        "sprint.py",
        "ui_run.py",
        "ui_test_case.py",
        "ui_test_suite.py",
    )
    schema_dir = PROJECT_ROOT / "src" / "testing_agent" / "schemas"

    for filename in expected_schema_files:
        assert (schema_dir / filename).exists(), f"schemas/{filename} is missing"

    for aggregate in ("assets.py", "context.py", "runs.py"):
        assert not (schema_dir / aggregate).exists()


def test_application_code_imports_split_models_and_schemas_directly():
    forbidden = (
        "from testing_agent.models.entities import",
        "from testing_agent.schemas.assets import",
        "from testing_agent.schemas.context import",
        "from testing_agent.schemas.runs import",
    )
    checked_dirs = ("handlers", "repositories", "routers", "services")

    for directory in checked_dirs:
        for path in (PROJECT_ROOT / "src" / "testing_agent" / directory).glob("*.py"):
            source = path.read_text(encoding="utf-8")
            for pattern in forbidden:
                assert pattern not in source, f"{path.name} still imports {pattern}"


def test_project_skill_storage_directory_is_kept_in_repository():
    skill_storage_dir = PROJECT_ROOT / "storage" / "skills"

    assert skill_storage_dir.exists()
    assert (skill_storage_dir / ".gitkeep").exists()


def test_context_routers_delegate_to_handlers():
    for router_name in ("auth.py", "projects.py", "sprints.py", "requirements.py"):
        source = (PROJECT_ROOT / "src" / "testing_agent" / "routers" / router_name).read_text(
            encoding="utf-8"
        )
        handler_module = router_name.removesuffix("s.py").removesuffix(".py")
        if router_name == "requirements.py":
            handler_module = "requirement"
        elif router_name == "projects.py":
            handler_module = "project"
        elif router_name == "sprints.py":
            handler_module = "sprint"
        assert f"testing_agent.handlers.{handler_module}" in source
        assert "testing_agent.services" not in source
        assert "testing_agent.api.deps" not in source
        assert "success_payload" not in source
