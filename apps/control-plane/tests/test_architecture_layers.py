import ast
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_generation_callers_cannot_reintroduce_the_aggregate_facade():
    root = PROJECT_ROOT / "src/testing_agent"
    assert not (root / "services/ai_generate_task.py").exists()
    for path in root.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.ImportFrom):
                assert node.module != "testing_agent.services.ai_generate_task"
                assert all(alias.name != "get_ai_generate_task_service" for alias in node.names)
            if isinstance(node, ast.ClassDef):
                assert node.name != "AiGenerateTaskService"
    for node in ast.walk(ast.parse((root / "services/ai_candidate_review.py").read_text())):
        if isinstance(node, ast.ImportFrom):
            assert node.module not in {
                "testing_agent.services.function_generate_import",
                "testing_agent.services.ui_generate_import",
                "testing_agent.services.api_generate_import",
            }, "Candidate review must not silently create formal assets"


def test_generation_queries_do_not_write_or_depend_on_task_command_facade():
    root = PROJECT_ROOT / "src/testing_agent"
    for name in ("ai_task_queries", "ai_task_scope"):
        for node in ast.walk(ast.parse((root / "services" / f"{name}.py").read_text())):
            if isinstance(node, ast.ImportFrom):
                assert node.module not in {
                    "testing_agent.services.ai_generate_task",
                    "testing_agent.services.ai_task_commands",
                    "testing_agent.services.ai_execution.writer",
                }
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                assert node.func.attr not in {"commit", "rollback", "add", "delete", "flush"}


def test_function_asset_modules_do_not_depend_on_export_or_api_collection():
    root = PROJECT_ROOT / "src/testing_agent"
    for name in ("function_test_case", "function_case_import", "function_case_access"):
        path = root / "services" / f"{name}.py"
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.ImportFrom):
                module = node.module or ""
                assert module != "testing_agent.services.api_collection"
                assert not module.startswith("testing_agent.services.zentao")
                assert module != "testing_agent.services.function_case_export"
    for node in ast.walk(ast.parse((root / "domain/function_case_export.py").read_text())):
        if isinstance(node, ast.ImportFrom):
            assert not (node.module or "").startswith(
                ("testing_agent.services", "testing_agent.repositories", "testing_agent.models")
            )
    for node in ast.walk(ast.parse((root / "services/function_case_export.py").read_text())):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            assert node.func.attr not in {"commit", "rollback"}, (
                "Remote export must not imply a local transaction can undo remote writes"
            )


def test_source_does_not_call_foreign_private_interfaces():
    root = PROJECT_ROOT / "src/testing_agent"
    for path in root.rglob("*.py"):
        tree = ast.parse(path.read_text())
        local = {"self", "cls"} | {
            node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)
        }
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("testing_agent"):
                assert all(not alias.name.startswith("_") for alias in node.names), (
                    f"{path}: import public interfaces only"
                )
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            method = node.func.attr
            if not method.startswith("_") or method.startswith("__"):
                continue
            receiver = ast.unparse(node.func.value)
            # urllib's parsed URL is a named tuple; _replace is its documented public API.
            if (
                path.relative_to(root).as_posix() == "services/zentao_auth.py"
                and receiver == "parsed"
                and method == "_replace"
            ):
                continue
            assert receiver in local, f"{path}:{node.lineno}: expose a public interface"


def test_shared_test_preparation_never_imports_collected_test_modules():
    assert not list((PROJECT_ROOT / "tests/support").rglob("test_*.py"))
    for path in (PROJECT_ROOT / "tests").rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            names = []
            if isinstance(node, ast.ImportFrom):
                names = [
                    node.module or "",
                    *(
                        (node.module + "." if node.module else "") + alias.name
                        for alias in node.names
                    ),
                ]
            elif isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            for name in names:
                assert not (
                    name.split(".")[0].startswith("test_") or name.startswith("tests.test_")
                ), f"{path}: move shared preparation into tests/support"


def test_business_deletion_is_explicit_and_storage_never_commits():
    root = PROJECT_ROOT / "src/testing_agent"
    for path in (root / "services").rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Attribute):
                assert node.attr != "hard_delete", (
                    f"{path.name}: use ResourceDeletion to make lifecycle coordination explicit"
                )
    for node in ast.walk(ast.parse((root / "repositories/deletion.py").read_text())):
        if isinstance(node, ast.Attribute):
            assert node.attr not in {"commit", "rollback"}
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id != "delete_resource", (
                "Storage recursion cannot invoke business commands"
            )


def test_bug_import_stages_do_not_depend_on_coordinator_or_mix_remote_and_local_writes():
    root = PROJECT_ROOT / "src/testing_agent/services/bug_import"
    for path in root.glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.ImportFrom):
                module = node.module or ""
                assert module != "testing_agent.services.zentao_bug_import"
                if path.name == "remote.py":
                    assert not module.startswith(
                        ("testing_agent.models", "testing_agent.repositories")
                    )
                if path.name == "writer.py":
                    assert module != "testing_agent.services.mcp_client"
            if path.name in {"prepare.py", "remote.py"} and isinstance(node, ast.Attribute):
                assert node.attr not in {"commit", "rollback"}, (
                    f"{path.name}: preparation does not own a write transaction"
                )


def test_provider_bindings_do_not_depend_on_the_binding_facade_or_each_other():
    root = PROJECT_ROOT / "src/testing_agent/services"
    for name in ("gitlab_bindings.py", "zentao_bindings.py"):
        for node in ast.walk(ast.parse((root / name).read_text())):
            if isinstance(node, ast.ImportFrom):
                assert node.module not in {
                    "testing_agent.services.resource_binding",
                    "testing_agent.services.gitlab_bindings",
                    "testing_agent.services.zentao_bindings",
                }, f"{name}: provider commands use the common access contract"


def test_provider_queries_do_not_import_connection_management_or_commit():
    root = PROJECT_ROOT / "src/testing_agent/services"
    for name in ("gitlab_queries.py", "zentao_queries.py"):
        for node in ast.walk(ast.parse((root / name).read_text())):
            if isinstance(node, ast.ImportFrom):
                assert node.module != "testing_agent.services.integration_connection"
            if isinstance(node, ast.Attribute):
                assert node.attr not in {"commit", "rollback"}, (
                    f"{name}: resource queries do not own business transactions; "
                    "Zentao refresh uses its explicitly injected authentication callback"
                )


def test_external_callers_do_not_use_connection_private_decryption():
    root = PROJECT_ROOT / "src/testing_agent"
    for path in root.rglob("*.py"):
        if path == root / "services/integration_connection.py":
            continue
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Attribute):
                assert node.attr != "_decrypt_secret", (
                    f"{path.name}: use the actor-bound public credential interface"
                )


def test_queue_identity_context_is_not_stored_as_orm_command_attributes():
    fields = {
        "suite_id",
        "case_id",
        "collection_run_id",
        "collection_id",
        "generate_task_id",
        "llm_connection_id",
    }
    root = PROJECT_ROOT / "src/testing_agent"
    tree = ast.parse((root / "models/worker_task.py").read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            assert not any(isinstance(t, ast.Name) and t.id in fields for t in node.targets)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            assert node.target.id not in fields
    for path in (root / "services").rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                if node.func.id == "WorkerTask":
                    assert not fields.intersection(k.arg for k in node.keywords), (
                        f"{path.name}: queue identities come from typed contexts; "
                        "new model choices belong to ExecutionIntent"
                    )


def test_worker_domains_do_not_depend_on_protocol_dispatch_or_other_domains():
    root = PROJECT_ROOT / "src/testing_agent/services/worker_domains"
    for path in root.glob("*.py"):
        allowed = {"testing_agent.services.worker_domains.events"}
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.ImportFrom):
                module = node.module or ""
                assert module not in {
                    "testing_agent.services.worker",
                    "testing_agent.services.worker_task",
                    "testing_agent.services.worker_domains",
                }, f"{path.name}: execution rules must not depend on their coordinator"
                if module.startswith("testing_agent.services.worker_domains."):
                    assert module in allowed, f"{path.name}: domains must remain independent"


def test_ai_repositories_do_not_hide_execution_writes_in_commit():
    for name in ("ai_generate_task.py", "worker_task.py"):
        path = PROJECT_ROOT / "src/testing_agent/repositories" / name
        tree = ast.parse(path.read_text())
        assert not any(
            isinstance(node, ast.AsyncFunctionDef) and node.name == "commit"
            for node in ast.walk(tree)
        ), f"{name}: execution commands, not repository.commit, own lifecycle writes"


def test_execution_commands_do_not_scan_sessions_or_use_orm_command_flags():
    root = PROJECT_ROOT / "src/testing_agent"
    flags = {
        "_operation",
        "_stage_review",
        "_worker_event",
        "_execution_state",
        "_actor",
        "_reset_requirement_review",
    }
    paths = [
        root / "services/ai_task_commands.py",
        root / "services/ai_candidate_review.py",
        root / "services/requirement_generate_import.py",
        root / "services/api_generate_import.py",
        root / "services/ui_generate_import.py",
        root / "services/function_generate_import.py",
        root / "services/ai_run_launcher.py",
        root / "services/ai_stage_workflow.py",
        root / "services/worker_task.py",
        root / "services/worker_authorization.py",
        *list((root / "services/ai_execution").glob("*.py")),
    ]
    for path in paths:
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Attribute):
                assert node.attr not in flags, f"{path.name}: use explicit ExecutionIntent"
                if path.parent.name == "ai_execution":
                    assert node.attr not in {"identity_map", "new"}, (
                        f"{path.name}: save a declared run rather than scanning the session"
                    )


def test_repositories_cannot_add_service_dependencies():
    for path in (PROJECT_ROOT / "src/testing_agent/repositories").rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            imports = []
            if isinstance(node, ast.ImportFrom) and node.module:
                imports = [node.module, *(node.module + "." + x.name for x in node.names)]
            elif isinstance(node, ast.Import):
                imports = [x.name for x in node.names]
            for module in imports:
                assert not module.startswith("testing_agent.services"), (
                    f"{path.name}: repository must not depend on {module}"
                )


def test_source_dependency_graph_has_no_module_cycles():
    root = PROJECT_ROOT / "src"
    files = list((root / "testing_agent").rglob("*.py"))
    assert files
    graph = {}
    for path in files:
        module = ".".join(path.relative_to(root).with_suffix("").parts).removesuffix(".__init__")
        package = module if path.name == "__init__.py" else module.rpartition(".")[0]
        dependencies = set()
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.ImportFrom):
                base = node.module or ""
                if node.level:
                    prefix = package.split(".")[: len(package.split(".")) - node.level + 1]
                    base = ".".join([*prefix, *([base] if base else [])])
                dependencies.add(base)
                dependencies.update(base + "." + item.name for item in node.names)
            elif isinstance(node, ast.Import):
                dependencies.update(item.name for item in node.names)
        graph[module] = dependencies
    visited, active = set(), []

    def visit(module):
        assert module not in active, " -> ".join([*active, module])
        if module in visited:
            return
        active.append(module)
        for dependency in sorted(graph[module] & graph.keys()):
            if dependency != module:
                visit(dependency)
        active.pop()
        visited.add(module)

    for module in sorted(graph):
        visit(module)


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
