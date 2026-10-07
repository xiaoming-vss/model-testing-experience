import hashlib
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from testing_agent_integration_worker.core.errors import PreflightError, WriteUncertain
from testing_agent_integration_worker.gateways.mcp import McpClient
from testing_agent_integration_worker.schemas.job import Access
from testing_agent_integration_worker.schemas.step import Operation, RemoteResult


def identifier(value: Any) -> int:
    try:
        number = int(value)
        if isinstance(value, (bool, float)) or not 0 < number <= 2_147_483_647:
            raise ValueError()
        return number
    except (ValueError, TypeError):
        raise PreflightError("remote_unavailable", "Remote resource ID is invalid") from None


def deleted(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def normalized_instance(value: str) -> str:
    url = urlsplit(value)
    if url.scheme not in {"http", "https"} or not url.hostname or url.username or url.password:
        raise PreflightError("baseline_changed", "MCP returned an invalid instance")
    host = url.hostname.lower()
    if ":" in host:
        host = "[" + host + "]"
    if url.port and (url.scheme, url.port) not in {("http", 80), ("https", 443)}:
        host += ":" + str(url.port)
    return urlunsplit((url.scheme.lower(), host, url.path.rstrip("/"), "", ""))


def instance_key(value: str) -> str:
    return hashlib.sha256(normalized_instance(value).encode()).hexdigest()


class ZentaoGateway:
    def __init__(self, access: Access, *, transport=None):
        self.client = McpClient(
            access.endpoint, access.token.get_secret_value(), transport=transport
        )

    async def __aenter__(self):
        await self.client.__aenter__()
        return self

    async def __aexit__(self, *args):
        await self.client.__aexit__(*args)

    async def verify_instance(self, target: dict[str, Any]) -> None:
        data = await self.client.call("get_zentao_instance", {})
        if (
            data.get("schemaVersion") != 1
            or not isinstance(data.get("instanceUrl"), str)
            or instance_key(data["instanceUrl"]) != instance_key(target["instanceUrl"])
        ):
            raise PreflightError(
                "baseline_changed", "MCP target no longer matches the frozen instance"
            )

    async def verify_target(self, target: dict[str, Any]) -> int:
        execution = (
            await self.client.call(
                "get_executions_executionID",
                {
                    "executionID": target["execution"],
                },
            )
        ).get("execution", {})
        story = (
            await self.client.call(
                "get_stories_storyID",
                {
                    "storyID": target["story"],
                },
            )
        ).get("story", {})
        if (
            identifier(execution.get("id")) != target["execution"]
            or identifier(execution.get("project")) != target["project"]
            or identifier(story.get("id")) != target["story"]
            or deleted(execution.get("deleted"))
            or deleted(story.get("deleted"))
        ):
            raise PreflightError("baseline_changed", "Remote execution or story changed")
        stories = (
            await self.client.call(
                "get_executions_executionID_stories",
                {
                    "executionID": target["execution"],
                },
            )
        ).get("stories", [])
        if isinstance(stories, dict):
            stories = list(stories.values())
        if not isinstance(stories, list) or not any(
            isinstance(item, dict) and str(item.get("id")) == str(target["story"])
            for item in stories
        ):
            raise PreflightError("baseline_changed", "Story no longer belongs to the execution")
        return identifier(story.get("product"))

    async def bug(self, remote_id: int, target: dict[str, Any], product_id=None) -> dict[str, Any]:
        remote = (await self.client.call("get_bugs_bugID", {"bugID": remote_id})).get("bug", {})
        if (
            not isinstance(remote, dict)
            or str(remote.get("id")) != str(remote_id)
            or deleted(remote.get("deleted"))
            or any(
                str(remote.get(key)) != str(target[key])
                for key in ("project", "execution", "story")
            )
            or (product_id is not None and str(remote.get("product")) != str(product_id))
        ):
            raise PreflightError("baseline_changed", "Original remote Bug no longer matches")
        return remote

    async def pages(self, tool: str, key: str, args: dict[str, Any]) -> list[dict[str, Any]]:
        if tool == "get_executions_executionID_builds":
            catalog = await self.client.list_tools()
            definition: dict[str, Any] = next(
                (item for item in catalog if item.get("name") == tool), {}
            )
            properties = definition.get("inputSchema", {}).get("properties", {})
            if not {"executionID", "pageID", "recPerPage"}.issubset(properties):
                raise PreflightError("remote_unavailable", "Build tool lacks paging support")
        results: list[dict[str, Any]] = []
        seen: set[str] = set()
        for page in range(1, 101):
            data = await self.client.call(tool, {**args, "pageID": page, "recPerPage": 100})
            batch = data.get(key)
            if isinstance(batch, dict):
                batch = list(batch.values())
            if not isinstance(batch, list) or any(
                not isinstance(item, dict) or "id" not in item for item in batch
            ):
                raise PreflightError("remote_unavailable", "Remote options have an invalid shape")
            unique = {str(identifier(item["id"])): item for item in batch}
            if seen.intersection(unique):
                raise PreflightError("remote_unavailable", "Paging returned duplicate rows")
            results.extend(unique.values())
            seen.update(unique)
            total = data.get("total", data.get("count"))
            if total is None and isinstance(data.get("pager"), dict):
                total = data["pager"].get("recTotal")
            if total is not None:
                try:
                    if isinstance(total, (bool, float)):
                        raise ValueError()
                    total = int(total)
                    if total < len(seen):
                        raise ValueError()
                except (ValueError, TypeError):
                    raise PreflightError(
                        "remote_unavailable", "Remote options have an invalid total"
                    ) from None
            if (total is not None and len(seen) == total) or (total is None and len(unique) < 100):
                return results
            if not batch:
                raise PreflightError("remote_unavailable", "Remote options are incomplete")
        raise PreflightError("remote_unavailable", "Remote options exceed the query limit")

    async def validate_choices(
        self, target: dict[str, Any], product: int, payload: dict[str, Any]
    ) -> None:
        builds = payload.get("openedBuild", ["trunk"])
        if builds != ["trunk"]:
            rows = await self.pages(
                "get_executions_executionID_builds",
                "builds",
                {
                    "executionID": target["execution"],
                },
            )
            allowed_builds = {
                str(row["id"])
                for row in rows
                if not deleted(row.get("deleted"))
                and all(
                    str(row.get(key)) == str(expected)
                    for key, expected in {
                        "project": target["project"],
                        "execution": target["execution"],
                        "product": product,
                    }.items()
                )
            }
            if not set(builds).issubset(allowed_builds):
                raise PreflightError("remote_rejected", "Selected builds are no longer valid")
        assignee = payload.get("assignedTo", "")
        if assignee:
            rows = await self.pages("get_users", "users", {"browseType": "inside"})
            allowed_users = {
                row.get("account")
                for row in rows
                if not deleted(row.get("deleted"))
                and not deleted(row.get("disabled"))
                and row.get("type", "inside") == "inside"
                and isinstance(row.get("account"), str)
                and 0 < len(row["account"]) <= 100
                and not any(char.isspace() or ord(char) < 32 for char in row["account"])
            }
            if assignee not in allowed_users or assignee in {"guest", "closed"}:
                raise PreflightError("remote_rejected", "Selected assignee is no longer available")

    async def file_info(self, remote_bug_id: int, remote_file_id: int) -> dict[str, Any]:
        file = (await self.client.call("get_files_fileID", {"fileID": remote_file_id})).get(
            "file", {}
        )
        if (
            not isinstance(file, dict)
            or identifier(file.get("id")) != remote_file_id
            or file.get("objectType") != "bug"
            or identifier(file.get("objectID")) != remote_bug_id
            or deleted(file.get("deleted"))
        ):
            raise PreflightError(
                "baseline_changed", "Native file no longer belongs to the original Bug"
            )
        return file

    async def write(self, operation: Operation) -> RemoteResult:
        data = await self.client.call(
            operation.tool, operation.arguments, write=True, timeout=operation.timeout_seconds
        )
        if (
            operation.tool in {"post_bugs", "upload_bug_attachment"}
            and data.get("status") != "success"
        ):
            raise WriteUncertain("Remote operation lacks an explicit success result")
        if operation.tool == "post_bugs":
            try:
                return RemoteResult(remote_bug_id=identifier(data.get("id")))
            except PreflightError as error:
                raise WriteUncertain("Creation lacks a valid remote ID") from error
        if operation.tool == "upload_bug_attachment":
            try:
                return RemoteResult(remote_file_id=identifier(data.get("id")))
            except PreflightError as error:
                raise WriteUncertain("Upload lacks a valid remote ID") from error
        return RemoteResult()
