## Problem Statement

TestPilot Studio 当前已具备 API 与功能用例生成任务能力，但 UI 用例生成仍是占位入口。用户无法基于项目源码创建 UI 候选用例，也无法在前端完成源码包上传、任务运行、候选结果编辑和人工审核。

后端已经提供 UI 用例生成任务、ZIP 源码包上传、运行、结果修改和审核接口。本规格先将这些能力接入现有统一生成任务工作台，并保持与现有 API/功能生成流程一致的状态、轮询、错误和审核体验；正式资产导入由后续规格补充。

## Solution

在现有统一生成任务列表中启用 UI 测试任务类型。用户创建 UI 生成任务时必须同时选择一个符合限制的 ZIP 源码包；前端先创建任务，再使用返回的任务 ID 上传源码包。完成后进入 UI 任务详情页，用户可以查看或替换源码包、选择 LLM 连接运行任务、查看运行历史、预览和编辑候选 YAML，并批准或拒绝候选结果。

源码包是 UI 生成任务唯一的生成来源。前端不展示或提交 `sourceContent`，不读取或解压源码包内容，也不调用任何内部 Worker 接口。审核完成后候选结果只读；本规格原始交付止于审核，后续导入能力见 `docs/specs/ui-approved-candidate-import.md`。

## User Stories

1. As a project member, I want UI generation tasks to appear alongside API and functional generation tasks, so that I can manage all AI generation work in one place.
2. As a project member, I want to identify UI tasks by a clear task-type label, so that I can distinguish them from API and functional tasks.
3. As a project member, I want to create a UI generation task from the existing new-task selector, so that I do not need to learn a separate entry point.
4. As a task creator, I want to provide a task name, sprint, and requirement, so that the task has complete business ownership.
5. As a task creator, I want the name, sprint, and requirement to be required, so that incomplete tasks are not deliberately created.
6. As a task creator, I want the generation instruction to be optional, so that the backend default strategy can be used when no extra instruction is needed.
7. As a task creator, I want to select the source ZIP in the creation form, so that creating the task and preparing its generation source feel like one workflow.
8. As a task creator, I want the creation form to reject a missing archive, so that a normally created task is ready to run.
9. As a task creator, I want non-ZIP files rejected before upload, so that I receive immediate feedback without an unnecessary request.
10. As a task creator, I want files larger than 100 MiB rejected before task creation, so that an invalid task is not created for a known client-side error.
11. As a task creator, I want the frontend to create the task before uploading the archive, so that it follows the backend task-scoped upload contract.
12. As a task creator, I want to enter the task detail page after creation and upload, so that I can continue directly to running the task.
13. As a task creator, I want a successfully created task to be preserved if its archive upload fails, so that I can retry without recreating task metadata.
14. As a task creator, I want the selected ZIP carried into the detail page after an immediate upload failure, so that I can retry during the same navigation.
15. As a task creator, I expect a page refresh to require selecting the local ZIP again, so that large local files are not persisted in browser or global state.
16. As a task owner, I want to see the active archive filename, formatted size, and upload time, so that I know which source version will be used.
17. As a task owner, I want SHA256 available in advanced details, so that I can verify the exact uploaded artifact when needed.
18. As a task owner, I want to replace an existing archive, so that future runs can use updated source code.
19. As a task owner, I want replacement to require confirmation showing the old and new filenames, so that I do not replace the active source accidentally.
20. As a task owner, I want replacement failure to leave the old archive visibly active, so that I understand no source change occurred.
21. As a task owner, I want archive replacement disabled while a run is pending, claimed, or running, so that source-version races are avoided.
22. As a task owner, I want archive replacement allowed after historical runs are finished or reviewed, so that later runs can use a newer source archive.
23. As a task owner, I want the UI to explain that archive replacement affects only future runs, so that I do not expect historical candidates to change.
24. As a task owner, I want the run button disabled when no archive exists, so that I know to upload a source ZIP first.
25. As a task owner, I want the disabled run action to explain“请先上传源码 ZIP”, so that the missing prerequisite is actionable.
26. As a task owner, I want to choose an active LLM connection before running, so that generation uses an explicitly selected model service.
27. As a task owner, I want the run request to send only `connectionId`, so that it conforms to the current published Swagger contract.
28. As a task owner, I want duplicate run submissions prevented while a run is in progress, so that the same task is not accidentally queued twice.
29. As a task owner, I want backend 400 errors for missing or invalid archives displayed, so that stale frontend state does not hide server truth.
30. As a task owner, I want to see pending, claimed, running, success, and failed run statuses, so that I can follow execution progress.
31. As a task owner, I want run history and the selected run detail to refresh automatically, so that long-running work updates without manual reload.
32. As a task owner, I want a manual refresh action, so that I can explicitly request the latest state.
33. As a user, I do not want internal Worker download URLs displayed or requested by the browser, so that internal infrastructure remains isolated.
34. As a reviewer, I want successful candidate results shown in a structured UI-case preview, so that I can review cases and steps without reading raw YAML only.
35. As a reviewer, I want access to the complete YAML editor, so that I can make precise changes without losing fields.
36. As a reviewer, I want the structured preview to parse standard YAML, so that the documented candidate format renders correctly.
37. As a reviewer, I want a parse failure to fall back to raw YAML rather than destroy or hide the candidate, so that malformed drafts remain recoverable.
38. As a reviewer, I want to save a modified candidate only while the run is successful and still pending review, so that reviewed results remain immutable.
39. As a reviewer, I want failed saves to preserve my unsaved editor content, so that backend validation errors do not erase work.
40. As a reviewer, I want unsaved changes to block approval or rejection, so that the reviewed version is unambiguous.
41. As a reviewer, I want a discard confirmation before closing an edited candidate, so that accidental loss is avoided.
42. As a reviewer, I want to approve a candidate with an optional review comment, so that accepted output can carry review context.
43. As a reviewer, I want to reject a candidate with an optional review comment, so that rejected output can carry feedback.
44. As a reviewer, I want only the existing approve and reject actions used, so that the UI matches the established review model.
45. As a reviewer, I want empty or whitespace-only result YAML to be ineligible for review, so that an empty candidate cannot become approved.
46. As a reviewer, I want approved and rejected candidates to become read-only immediately, so that review completion freezes the result.
47. As a reviewer, I want an approved run to show approved and pending-import states, so that review and formal asset import remain distinct concepts.
48. As a reviewer, I do not want an import button after approval, so that this release stops at candidate review.
49. As an unauthorized user, I want list or detail access failures to show a blocking permission state, so that protected data is not rendered.
50. As an unauthorized user, I want mutation permission failures distinguished from field validation, so that I understand the action is forbidden.
51. As an editor, I want my selected file or YAML draft preserved after a forbidden mutation, so that a permission response does not clear local work.
52. As a user, I want 400, 403, 404, and 413 upload errors to retain the backend message, so that specific archive failures remain understandable.
53. As a user, I want 413 to be described as a file-size limit failure, so that gateway rejection is not presented as a generic server error.
54. As a user, I want upload controls disabled during upload, so that duplicate uploads are prevented.
55. As a user, I accept an overall uploading state without byte-level progress in this release, so that the existing request client can be reused.
56. As a maintainer, I want product and system documentation updated when the feature ships, so that UI generation is no longer documented as Coming Soon.
57. As a maintainer, I want tests to verify that no request targets `/internal/ai-worker/**`, so that the frontend/backend trust boundary remains enforced.
58. As a maintainer, I want UI generation to reuse existing task statuses, polling, authentication, error envelopes, and LLM selection, so that behavior remains consistent.
59. As a maintainer, I want server state kept in React Query and transient UI state kept local, so that no unnecessary global store is introduced.
60. As a maintainer, I want the source archive treated as the canonical UI-generation source rather than `sourceContent`, so that the frontend matches the backend domain model.

## Implementation Decisions

- UI generation tasks join the current unified API/functional/UI task list; separate task tabs are not restored.
- The existing disabled UI option becomes available in the new-task selector.
- UI task detail uses a dedicated route parallel to existing generation-task detail routes.
- All operations use the published user-facing v1 task, archive, run, result, and review endpoints.
- The task model includes nullable `sourceArchive` metadata: archive ID, filename, byte size, SHA256, and upload time.
- `sourceType` and `sourceContent` are not shown or sent. `sourceContent` is not a fallback.
- Creation requires task name, sprint, requirement, and ZIP; generation instruction is optional.
- Before task creation, the file must end in `.zip` and must not exceed 100 MiB.
- Creation is a non-atomic two-request workflow: create task, then upload using multipart field `file`.
- If creation succeeds and upload fails, retain the task and navigate to detail for retry; never auto-delete it.
- A selected `File` may pass only through transient navigation state for immediate retry and is lost on refresh.
- Successful creation/upload navigates directly to task detail.
- Upload success replaces task detail cache with the returned task and `sourceArchive`.
- Existing archives display filename, formatted size, upload time, and advanced SHA256.
- Replacing an archive requires confirmation showing old/new filenames; first upload to an empty task does not.
- Replacement is disabled while any run is pending, claimed, or running.
- Historical finished/reviewed runs do not block replacement; replacement affects future runs only.
- Upload reuses the fetch client and shows overall loading only; byte progress is not added.
- Backend archive error messages are preserved; HTTP 413 receives explicit size-limit framing.
- Running requires a non-null source archive and no in-progress run.
- The active-LLM selection modal is reused.
- Run requests contain `connectionId` only. Runtime `instruction` is excluded because current Swagger does not declare it and forbids additional properties.
- Existing task status vocabulary, run list/detail queries, and polling are reused.
- Snapshot fields containing internal Worker URLs are neither rendered nor requested.
- Candidate eligibility requires `status=success`, `reviewStatus=pending`, and nonblank `resultYaml`.
- Candidate review has “预览候选” and “编辑 YAML” views.
- Add a maintained YAML parser as a direct dependency; parse failure falls back to raw YAML.
- The complete YAML remains the persistence unit. Unknown candidate fields are not normalized away before saving.
- Unsaved edits survive save failures; review is unavailable until changes are saved or discarded.
- Review actions are exactly `approve` and `reject`, with optional `reviewComment`.
- Successful review updates the selected run immediately and freezes editing.
- Approval displays approved and pending-import states；后续规格在满足严格资格时增加导入控制。
- Query 403 errors show a blocking no-access state and suppress protected content.
- Mutation 403 errors preserve safe local state and use explicit permission language.
- Server state remains in React Query; forms, selected files, modal state, selected runs, and drafts stay local or transient.
- Product documentation and system design are updated for the unified list and completed UI generation/review flow.
- 本规格交付时不调用 UI 套件导入端点；后续实现以 `docs/specs/ui-approved-candidate-import.md` 为准。

## Testing Decisions

- Tests assert external behavior rather than component state, hook internals, or cache implementation details.
- The primary seam is high-level page rendering with router, QueryClient, theme provider, mocked fetch, and real user-event interactions.
- The unified task page is tested through UI task creation, validation, request payloads, two-stage create/upload, navigation, and permissions.
- The detail page is tested through archive display/replacement, run eligibility, LLM selection, statuses, candidate save, review, read-only state, and permissions.
- Existing API and functional detail tests are prior art for fetch-envelope mocks, URL/body assertions, run rendering, draft preservation, and review transitions.
- Pure-function tests are limited to ZIP validation, YAML parsing/fallback, structured candidate mapping, and formatting.
- Tests cover omission of `sourceType` and `sourceContent`.
- Tests cover required requirement and ZIP, invalid extension, and files over 100 MiB without network requests.
- Tests verify PUT multipart upload field `file`, successful upload/replacement, replacement confirmation, old-archive preservation on failure, and active-run replacement blocking.
- Tests cover creation success followed by upload failure, detail navigation, transient retry, and refresh reselection.
- Tests cover missing-archive run guidance and backend 400 handling.
- Tests cover pending, claimed, running, success, and failed states.
- Tests cover YAML edit/save, failed-save draft preservation, structured nested-step preview, and raw fallback.
- Tests cover approve/reject values, empty-result ineligibility, and reviewed-result read-only behavior；导入控制由后续规格单独覆盖。
- Tests cover query and mutation 403 behavior plus archive 400, 404, and 413 errors.
- Covered workflows fail if any request targets `/internal/ai-worker/**`.
- Backend ZIP extraction security is not tested in the browser.
- Final verification runs type checking, lint, the full automated test suite, and production build.

## Out of Scope

- Importing approved UI candidates into UI test suites（此项仅对本规格原始范围成立，后续由 `ui-approved-candidate-import.md` 实现）。
- Automatically importing after approval；后续导入仍必须由用户显式发起。
- Reading, previewing, indexing, or extracting files inside the ZIP in the browser.
- Calling `/internal/ai-worker/**`.
- Selecting or freezing a requirement-document version.
- Sending a per-run instruction until Swagger supports it.
- Byte-level upload progress or a new XHR upload client.
- Persisting local ZIP files across refresh or browser sessions.
- Changing historical runs when an archive is replaced.
- Creating a global permission framework or global task store.
- Reintroducing separate API/UI/functional task tabs.

## Further Notes

- 源码包是 UI 用例生成任务唯一的生成来源，可被后续上传替换；替换失败时原源码包仍有效。
- 后端校验是压缩包完整性、解压后大小、文件数、路径穿越、绝对路径、符号链接、重复路径、候选 YAML 结构及资源归属的最终事实。
- OpenAPI 将任务请求字段声明为 nullable，但前端采用已经确认的更严格业务校验。
- 当前 OpenAPI 运行 schema 不支持 `instruction`，因此本次前端不发送该字段。
- 页面保持“审核”与“正式资产导入”的领域边界：审核不会自动导入，后续导入是独立显式操作。
- 已确认的主要测试接缝是页面边界与 mock HTTP，只有文件校验和 YAML 解析使用窄纯函数接缝。
