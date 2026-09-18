# 已审核 UI 候选用例导入现有 UI 测试套件

## Problem Statement

UI 用例生成任务已经能够从源码包产出候选结果，并支持编辑、批准和拒绝，但审核通过只是候选生命周期中的一个独立动作，用户仍无法将已批准候选写入正式 UI 测试资产。用户需要离开生成工作区并手工搬运用例，既容易丢失完整步骤字段，也无法安全处理同名正式用例。

用户需要在 UI 生成任务详情中选择当前需求下已有且归自己所有的 UI 测试套件，将符合资格的已批准候选整批导入。发生同名冲突时，用户必须在零写入状态下查看全部差异，再决定是否整批原位覆盖。导入成功、失败、取消和并发操作都必须保持审核与正式资产导入之间的领域边界，并准确反映后端运行状态。

## Solution

在 UI 用例生成任务详情的所选运行候选结果区域中加入正式资产导入流程。仅当运行成功、审核已批准且导入待处理时提供入口。用户在独立弹窗中从该运行需求下搜索并选择已有 UI 测试套件，然后发起首次导入。

无冲突时，页面立即使用响应中的运行更新导入状态，展示导入时间和目标套件，并禁止再次导入。存在冲突时，页面进入冲突预览：完整展示所有同名正式用例与候选用例，包括已知步骤字段、未知步骤字段和完整原始步骤数据，但不执行任何正式资产写入。用户可以取消并稍后重试，也可以确认整批覆盖；确认后前端使用同一目标套件重新请求，后端负责重新检查、原位覆盖、追加非冲突候选和事务回滚。

失败时在当前交互上下文中展示准确错误，保留目标套件和冲突信息以便重试。页面在打开导入交互、重新聚焦、手工刷新以及重复导入错误后重新确认运行状态，从而处理其他请求已经完成导入的情况，而不为已完成运行增加持续轮询。

## User Stories

1. As an UI 候选审核者, I want to import an approved candidate result into a formal UI test suite, so that I do not need to copy cases manually.
2. As an UI 候选审核者, I want the import action to appear only for successful, approved, pending-import runs, so that I cannot start an invalid import.
3. As an UI 候选审核者, I want unsuccessful or unapproved runs to omit the import action, so that the difference between审核 and正式资产导入 remains clear.
4. As an UI 候选审核者, I want imported runs to show a read-only imported state, so that the same run cannot be submitted twice.
5. As an UI 候选审核者, I want the run history to show each run's import status, so that I can understand the complete lifecycle at a glance.
6. As an UI 候选审核者, I want to choose a target suite in a dedicated modal, so that the import decision is explicit and focused.
7. As an UI 候选审核者, I want to search the available suites by text, so that I can find the intended suite efficiently.
8. As an UI 候选审核者, I want to see only suites under the run's requirement, so that candidates cannot be intentionally sent across requirements.
9. As an UI 候选审核者, I want an empty-state message when the requirement has no suite, so that I understand why import cannot continue.
10. As an UI 候选审核者, I want suite-list permission and loading failures to remain in the selection modal, so that the task page context is preserved.
11. As an UI 候选审核者, I want the first import request to explicitly be a non-overwrite attempt, so that conflicts are previewed before any destructive decision.
12. As an UI 候选审核者, I want a no-conflict import to finish directly, so that safe imports do not require an unnecessary second confirmation.
13. As an UI 候选审核者, I want all same-name conflicts to be shown, so that I can assess the full impact of an overwrite.
14. As an UI 候选审核者, I want each conflict to identify its sequence, candidate name, and normalized name, so that similarly named cases remain distinguishable.
15. As an UI 候选审核者, I want existing and generated cases compared side by side on wide screens, so that differences are easy to scan.
16. As an UI 候选审核者, I want the comparison to stack on narrow screens, so that all content remains readable without horizontal loss.
17. As an UI 候选审核者, I want conflicts presented as an expandable list, so that a large conflict set remains navigable without forcing a wizard sequence.
18. As an UI 候选审核者, I want the first conflict expanded by default and every other conflict title visible, so that I can immediately inspect one item while retaining an overview.
19. As an UI 候选审核者, I want complete name, enabled, order number, and step data for both sides, so that the overwrite decision is informed.
20. As an UI 候选审核者, I want enabled and continue-on-failure values translated into readable labels, so that boolean fields have clear business meaning.
21. As an UI 候选审核者, I want missing, null, and empty-string values shown differently, so that meaningful data differences are not hidden.
22. As an UI 候选审核者, I want long URLs, locators, and operation values shown completely, so that critical step details are not truncated.
23. As an UI 候选审核者, I want unknown step fields shown separately, so that newer or extension fields are never silently discarded.
24. As an UI 候选审核者, I want access to the complete original steps data, so that I can verify the lossless representation.
25. As an UI 候选审核者, I want conflict preview to perform zero formal-asset writes, so that reviewing conflicts cannot partially change the suite.
26. As an UI 候选审核者, I want to cancel conflict overwrite without sending another request, so that approval remains intact and I can reconsider later.
27. As an UI 候选审核者, I want one explicit whole-batch overwrite confirmation, so that the interface matches the backend's atomic import capability.
28. As an UI 候选审核者, I want the confirmation text to explain replacement, addition, and rollback semantics, so that I understand the full batch impact.
29. As an UI 候选审核者, I want the confirmation request to reuse the previewed suite, so that the reviewed conflict set and target do not diverge.
30. As an UI 候选审核者, I want changed conflicts returned during confirmation to replace the preview and require another confirmation, so that stale approval is never applied automatically.
31. As an UI 候选审核者, I want all import and confirmation controls disabled while a request is active, so that accidental duplicate submissions are prevented.
32. As an UI 候选审核者, I want backend duplicate-import errors shown correctly, so that frontend guarding never hides the authoritative result.
33. As an UI 候选审核者, I want 400, 403, 404, and 500 failures distinguished, so that I know whether the problem is business eligibility, permission, missing data, or service failure.
34. As an UI 候选审核者, I want my selected suite preserved after failure or cancellation during the current page session, so that retrying does not require repetitive selection.
35. As an UI 候选审核者, I want stale suite selections cleared when the suite no longer exists in the refreshed list, so that I cannot unknowingly retry an invalid target.
36. As an UI 候选审核者, I want a successful response to update the selected run immediately, so that the import action disappears without waiting for a later refresh.
37. As an UI 候选审核者, I want the run history to update after success, so that detail and history do not display contradictory statuses.
38. As an UI 候选审核者, I want the imported time and target suite displayed after success, so that the formal asset destination is traceable.
39. As an UI 候选审核者, I want to remain in the generation task after import, so that I retain the run and review context.
40. As an UI 候选审核者, I want a direct action to open the formal UI suite, so that I can inspect the imported cases when desired.
41. As an UI 候选审核者, I want the page to recheck the run before opening import, so that an import completed elsewhere is recognized.
42. As an UI 候选审核者, I want a duplicate-import response followed by an imported refresh to be presented as an externally completed import, so that I do not repeatedly retry completed work.
43. As an UI 候选审核者, I want a duplicate-import response followed by a still-pending refresh to remain retryable, so that an unrelated 400 does not freeze the workflow.
44. As an UI 候选审核者, I want审核状态 to remain approved after preview, cancellation, or failure, so that正式资产导入 never reverses the审核 decision.
45. As a product maintainer, I want the UI flow to rely only on import status, imported targets, and imported time, so that legacy collection identifiers do not leak into UI-suite import behavior.
46. As a product maintainer, I want existing API and functional compatibility fields left untouched, so that this UI-specific change does not destabilize other generation flows.

## Implementation Decisions

- The import entry belongs only to the selected run's candidate-result area within the existing UI generation task detail. The run-history table gains an import-status column but no duplicate action.
- Eligibility is exactly `status=success`, `reviewStatus=approved`, and `importStatus=pending`. `importStatus=imported` is sufficient to prevent another import even if optional display metadata is absent.
- The target selection uses a dedicated modal with a searchable select control. It lists only existing suites returned for the run requirement and does not support manual IDs, cross-requirement selection, or suite creation.
- Suite lookup uses the selected run's requirement identifier first and may fall back to the task's current requirement identifier when the run identifier is absent. Historical requirement reassignment risk is not handled separately in this scope.
- The first request sends `suiteId` and explicitly sends `confirmOverwrite=false`.
- The import response is read from the common response envelope and modeled as a discriminated interaction using `requiresConfirmation`, `conflicts`, and `run`.
- A response with `requiresConfirmation=false` completes the import. The returned run immediately replaces the selected run server state, and the run list is synchronized or invalidated.
- A response with `requiresConfirmation=true` enters conflict preview and is not treated as an error or success. No formal case API is called by the browser during preview.
- Conflict response models are separate from existing formal-case editing models because conflict `stepsJson` is structured data while existing formal-case APIs currently expose a serialized representation.
- Conflict step values preserve unknown keys through an open-ended record shape. Rendering derives known fields without normalizing, mutating, or resubmitting the conflict payload.
- Every conflict is represented in an expandable list. The first item opens by default; users may open any number of items. A fixed modal action area remains accessible for large lists.
- Existing and generated cases are compared side by side at wide breakpoints and stacked at narrow breakpoints.
- Known fields receive readable Chinese labels. Missing values, null values, and empty strings have distinct representations. Long text wraps without content truncation.
- Unknown fields are rendered per step in an additional JSON area, and the complete original `stepsJson` is available in a collapsible raw view.
- Overwrite confirmation is whole-batch only. The UI does not offer per-conflict selection because the backend contract supports only one atomic confirmation.
- The confirmation request sends the same `suiteId` and `confirmOverwrite=true`. The browser does not delete, recreate, or patch formal cases directly.
- If a confirmation response again requires confirmation, its latest conflict set replaces the previous view, an explicit changed-conflict notice appears, and another user confirmation is required. No automatic request loop is allowed.
- Selection-modal cancellation sends no import request. Conflict-modal cancellation sends no confirmation request. Both preserve the approved review state.
- A selected suite is retained per run in page-local state after import errors or conflict cancellation. It is not persisted across refresh or navigation. A refreshed suite list removes a selection that is no longer available.
- Suite-list errors and first-request errors render in the selection modal. Confirmation errors render in the conflict modal without discarding conflict content.
- HTTP 403 is presented as a permission failure rather than validation. HTTP 404 distinguishes missing run and missing suite where the backend message permits, then refreshes relevant server state. HTTP 400 preserves the backend business message. HTTP 500 communicates server failure and retains retry state.
- Import and confirmation buttons, relevant cancellation controls, and target changes are disabled during active requests.
- Completed runs do not gain continuous polling. Run state is refreshed before opening import, on normal focus refresh, on manual refresh, and after a duplicate-import 400.
- When refresh after a duplicate-import response returns `imported`, import UI closes and the page reports that another operation completed the import. When it remains `pending`, the original error remains retryable.
- Successful import keeps the user on the generation task detail, displays imported time and the `ui_suite` target, and exposes a navigation action to the existing formal suite detail route.
- The generation detail does not query formal cases after success because it does not render a formal case list. The destination suite detail owns the latest formal-case query.
- API, functional, and UI generation runs share the array-based imported-target lifecycle; UI import reads only the `ui_suite` target and never falls back to a single-target field.
- The UI generation API module gains the run-import operation, and generation-domain types gain the request, response, conflict-case, and open-ended step contracts.
- Existing product, system-design, and prior UI-generation specifications are updated to replace the former “no UI import” scope with the completed formal-asset-import lifecycle.

## Testing Decisions

- Tests assert externally observable behavior: visible controls and messages, modal contents, navigation, request URLs, request bodies, and request counts. They do not assert component state, hook internals, or React Query cache implementation.
- The primary and only new test seam is the existing high-level UI generation task detail page rendered with a real router, React Query provider, component tree, mocked HTTP boundary, and real user interactions.
- Existing UI generation task detail tests provide prior art for fetch-envelope mocks, selected-run behavior, permission failures, candidate review, and read-only transitions.
- Existing API and functional candidate-import tests provide prior art for eligibility, response-driven state replacement, conflict requests, cancellation, overwrite confirmation, and legacy-field isolation, but UI behavior remains covered through the UI page seam.
- Tests cover hidden or disabled import behavior for every ineligible combination and enabled behavior only for `success + approved + pending`.
- Tests cover requirement-scoped suite loading, searching, empty state, stale selection clearing, and suite-query errors.
- Tests cover a no-conflict response, immediate selected-run update, run-history update, duplicate prevention, imported-time display, target display, and navigation to the formal suite.
- Tests cover a conflict response with multiple conflicts and assert that the first request makes no formal-case write calls.
- Tests cover complete case fields, every known step field, unknown step fields, raw steps data, long values, and distinct missing/null/empty-string rendering.
- Tests cover conflict cancellation without a confirmation request, retained approval, retained suite selection, and later retry.
- Tests cover overwrite confirmation using the same suite and `confirmOverwrite=true`.
- Tests cover changed conflicts returned during confirmation, replacement of displayed conflicts, and the requirement for another manual confirmation.
- Tests cover active-request disabling and prevention of duplicate submissions.
- Tests cover 400, 403, 404, and 500 in the appropriate modal, retained safe state, and retry behavior.
- Tests cover a duplicate-import 400 followed by an imported refresh and by a still-pending refresh.
- Tests cover page focus or explicit refresh updating an externally imported run to read-only imported state.
- Tests verify that UI import eligibility and target display use `importStatus` and the `ui_suite` entry in `importedTargets`.
- Tests verify that the browser calls only the run-import endpoint for formal-asset import and never calls formal-case delete, create, or update APIs to simulate overwrite.
- Preserving an existing formal case ID during overwrite is a backend integration-test responsibility because the import response does not return formal cases and the generation detail does not load them.

## Out of Scope

- Automatically creating a UI test suite.
- Creating a suite from the target-selection modal.
- Selecting a suite from another requirement.
- Manually entering a suite identifier.
- Per-conflict selection, partial import, or skipping individual conflicts.
- Editing candidate or formal cases inside the conflict preview.
- Displaying the full formal-case list on the generation task detail.
- Querying formal cases before and after import solely to verify case identifiers.
- Continuous polling of completed runs.
- Persisting the selected suite across refresh, navigation, or browser sessions.
- Removing legacy compatibility fields from API or functional generation types.
- Changing backend conflict normalization, transaction, rollback, overwrite, or ownership behavior.

## Further Notes

- The domain terms remain distinct: a候选结果 is editable only before审核;审核 approval does not create a formal asset;正式资产导入 is a later operation;冲突预览 is a zero-write confirmation state rather than an import failure.
- The backend is authoritative for ownership, eligibility, duplicate prevention, conflict rechecking, complete rollback, and preservation of existing formal case IDs.
- The frontend must preserve backend business messages for invalid candidates and duplicate imports while still mapping permission, missing-resource, and server failures to clear interaction contexts.
- The previous UI generation scope deliberately excluded formal suite import. This specification supersedes only that exclusion and leaves source archive, generation, candidate editing, and review behavior intact.
