from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from http import HTTPStatus
from typing import Any


@dataclass(slots=True)
class AppError(Exception):
    code: int
    message: str
    http_code: int = HTTPStatus.INTERNAL_SERVER_ERROR
    data: Any | None = None

    def __call__(self) -> AppError:
        """Create a request-local exception from a shared error definition."""
        return AppError(self.code, self.message, self.http_code, self.data)

    def __str__(self) -> str:
        return self.message


ErrSuccess = AppError(0, "ok", HTTPStatus.OK)
ErrBadRequest = AppError(400, "请求参数错误", HTTPStatus.BAD_REQUEST)
ErrUnauthorized = AppError(401, "未授权或登录失效", HTTPStatus.UNAUTHORIZED)
ErrForbidden = AppError(403, "无权操作该资源", HTTPStatus.FORBIDDEN)
ErrNotFound = AppError(404, "资源不存在", HTTPStatus.NOT_FOUND)
ErrInternalServerError = AppError(500, "服务器内部错误", HTTPStatus.INTERNAL_SERVER_ERROR)

ErrNameAlreadyUse = AppError(1001, "该用户名已被注册", HTTPStatus.CONFLICT)
ErrEmailAlreadyUse = AppError(1002, "该邮箱已被注册", HTTPStatus.CONFLICT)
ErrPasswordChangeRequired = AppError(
    1003, "首次登录必须修改密码后才能继续操作", HTTPStatus.FORBIDDEN
)
ErrAccountDisabled = AppError(1004, "账号已被禁用，请联系系统管理员", HTTPStatus.FORBIDDEN)
ErrAccountLocked = AppError(1005, "登录失败次数过多，账号已临时锁定", HTTPStatus.LOCKED)
ErrTooManyLoginAttempts = AppError(
    1006, "登录尝试过于频繁，请稍后再试", HTTPStatus.TOO_MANY_REQUESTS
)
ErrPasswordTooShort = AppError(1007, "密码至少需要 10 个字符", HTTPStatus.BAD_REQUEST)
ErrPasswordTooLong = AppError(1008, "密码长度不能超过 72 个字节", HTTPStatus.BAD_REQUEST)
ErrPasswordSameAsOld = AppError(1009, "新密码不能与旧密码相同", HTTPStatus.BAD_REQUEST)
ErrOldPasswordInvalid = AppError(1010, "旧密码不正确", HTTPStatus.BAD_REQUEST)
ErrUsernameImmutable = AppError(1011, "用户名创建后不允许修改", HTTPStatus.BAD_REQUEST)
ErrEmailRequired = AppError(1012, "邮箱为必填项", HTTPStatus.BAD_REQUEST)
ErrSuperAdminProtected = AppError(1013, "系统超级管理员不允许禁用或删除", HTTPStatus.FORBIDDEN)
ErrCannotDeleteSelf = AppError(1014, "不能删除当前登录账号", HTTPStatus.BAD_REQUEST)
ErrCannotDisableSelf = AppError(1015, "不能禁用当前登录账号", HTTPStatus.BAD_REQUEST)
ErrLdapUnavailable = AppError(
    1020, "LDAP 服务不可用或目录配置尚未验证", HTTPStatus.SERVICE_UNAVAILABLE
)
ErrLdapConflict = AppError(1021, "LDAP 身份或资料冲突，请检查目录与平台账号", HTTPStatus.CONFLICT)
ErrLdapReadOnly = AppError(1022, "LDAP 用户身份资料由目录管理，平台不可修改", HTTPStatus.FORBIDDEN)
ErrLdapPending = AppError(1023, "账号待 LDAP 关联，请使用 LDAP 登录", HTTPStatus.FORBIDDEN)
ErrLocalLoginRestricted = AppError(1024, "本地登录仅供系统管理员使用", HTTPStatus.FORBIDDEN)
ErrRegistrationClosed = AppError(1025, "当前认证模式不允许自助注册", HTTPStatus.FORBIDDEN)
ErrLdapCutoverRequired = AppError(1026, "LDAP 认证切换尚未完成", HTTPStatus.SERVICE_UNAVAILABLE)
ErrProjectNameAlreadyUse = AppError(2001, "该项目名称已存在", HTTPStatus.CONFLICT)
ErrProjectSkillSpaceNotFound = AppError(2002, "项目技能包不存在", HTTPStatus.NOT_FOUND)
ErrProjectSkillSpaceFileRequired = AppError(2003, "请上传技能压缩包", HTTPStatus.BAD_REQUEST)
ErrProjectSkillSpaceFileInvalid = AppError(
    2004, "技能压缩包类型不合法，仅支持 zip/tar", HTTPStatus.BAD_REQUEST
)
ErrProjectSkillSpaceDefaultProtected = AppError(
    2005, "默认技能包不允许删除", HTTPStatus.BAD_REQUEST
)
ErrSprintNotFound = AppError(2101, "迭代不存在", HTTPStatus.NOT_FOUND)
ErrSprintNameAlreadyUse = AppError(2102, "该迭代名称已存在", HTTPStatus.CONFLICT)
ErrSprintDailyMetricsNotFound = AppError(2103, "迭代每日统计不存在", HTTPStatus.NOT_FOUND)
ErrSprintDailyMetricsDateInvalid = AppError(2104, "统计日期格式不合法", HTTPStatus.BAD_REQUEST)
ErrSprintDailyMetricsValueInvalid = AppError(2105, "统计值不合法", HTTPStatus.BAD_REQUEST)
ErrSprintScheduleInvalid = AppError(
    2106, "迭代开始和结束时间必须包含时区，且结束时间晚于开始时间", HTTPStatus.BAD_REQUEST
)
ErrRequirementFileMissing = AppError(2203, "需求原文件未存储到 S3，请重新上传", HTTPStatus.CONFLICT)
ErrRequirementNotFound = AppError(2201, "需求不存在", HTTPStatus.NOT_FOUND)
ErrRequirementNameAlreadyUse = AppError(2202, "该需求名称已存在", HTTPStatus.CONFLICT)
ErrApiCollectionNotFound = AppError(2301, "API集合不存在", HTTPStatus.NOT_FOUND)
ErrApiCollectionNameAlreadyUse = AppError(2302, "该API集合名称已存在", HTTPStatus.CONFLICT)
ErrApiCollectionRunNotFound = AppError(2303, "API集合运行记录不存在", HTTPStatus.NOT_FOUND)
ErrApiCollectionRunEnvironmentMismatch = AppError(
    2304, "API集合与环境不属于同一项目", HTTPStatus.BAD_REQUEST
)
ErrApiCollectionImportInvalid = AppError(2305, "API集合导入内容不合法", HTTPStatus.BAD_REQUEST)
ErrApiCollectionImportFileRequired = AppError(2306, "请上传YAML文件", HTTPStatus.BAD_REQUEST)
ErrApiCaseNotFound = AppError(2401, "API用例不存在", HTTPStatus.NOT_FOUND)
ErrApiCaseNameAlreadyUse = AppError(2402, "该API用例名称已存在", HTTPStatus.CONFLICT)
ErrApiCaseRunEnvironmentMismatch = AppError(
    2403, "API用例与环境不属于同一项目", HTTPStatus.BAD_REQUEST
)
ErrApiCaseRunNotFound = AppError(2404, "API用例运行记录不存在", HTTPStatus.NOT_FOUND)
ErrApiWorkerTaskNotFound = AppError(2405, "API Worker任务不存在", HTTPStatus.NOT_FOUND)
ErrApiEnvironmentNotFound = AppError(2501, "API环境不存在", HTTPStatus.NOT_FOUND)
ErrApiEnvironmentNameAlreadyUse = AppError(2502, "该API环境名称已存在", HTTPStatus.CONFLICT)
ErrApiEnvironmentVarNotFound = AppError(2601, "API环境变量不存在", HTTPStatus.NOT_FOUND)
ErrApiEnvironmentVarNameAlreadyUse = AppError(2602, "该API环境变量名已存在", HTTPStatus.CONFLICT)
ErrApiAssertRuleNotFound = AppError(2701, "API断言规则不存在", HTTPStatus.NOT_FOUND)
ErrApiAssertRuleNameAlreadyUse = AppError(2702, "该API断言规则名称已存在", HTTPStatus.CONFLICT)
ErrApiExtractRuleNotFound = AppError(2801, "API提取规则不存在", HTTPStatus.NOT_FOUND)
ErrApiExtractRuleVarKeyAlreadyUse = AppError(2802, "API提取变量名已存在", HTTPStatus.CONFLICT)
ErrUiTestSuiteNotFound = AppError(2901, "UI测试集不存在", HTTPStatus.NOT_FOUND)
ErrUiTestSuiteNameAlreadyUse = AppError(2902, "该UI测试集名称已存在", HTTPStatus.CONFLICT)
ErrUiTestSuiteImportInvalid = AppError(2903, "UI测试集导入内容不合法", HTTPStatus.BAD_REQUEST)
ErrUiTestSuiteImportFileRequired = AppError(2904, "请上传YAML文件", HTTPStatus.BAD_REQUEST)
ErrUiTestCaseNotFound = AppError(3001, "UI测试用例不存在", HTTPStatus.NOT_FOUND)
ErrUiTestCaseNameAlreadyUse = AppError(3002, "该UI测试用例名称已存在", HTTPStatus.CONFLICT)
ErrUiTestCaseRunNotFound = AppError(3003, "UI测试用例运行记录不存在", HTTPStatus.NOT_FOUND)
ErrUiWorkerTaskNotFound = AppError(3004, "UI Worker任务不存在", HTTPStatus.NOT_FOUND)
ErrUiTestSuiteRunNotFound = AppError(3005, "UI测试集运行记录不存在", HTTPStatus.NOT_FOUND)
ErrUiTestSuiteRunItemNotFound = AppError(3006, "UI测试集运行子项不存在", HTTPStatus.NOT_FOUND)
ErrApiCaseGenerateTaskNotFound = AppError(3101, "API用例生成任务不存在", HTTPStatus.NOT_FOUND)
ErrAiGenerateTaskRunNotFound = AppError(3102, "API用例生成任务运行记录不存在", HTTPStatus.NOT_FOUND)
ErrAiWorkerTaskNotFound = AppError(3103, "AI Worker任务不存在", HTTPStatus.NOT_FOUND)
ErrAiGenerateTaskRunReviewed = AppError(3104, "该运行记录已审核", HTTPStatus.BAD_REQUEST)
ErrAiGenerateTaskRunRunning = AppError(3106, "运行中的记录不允许删除", HTTPStatus.CONFLICT)
ErrFunctionCaseGenerateTaskNotFound = AppError(3105, "功能测试AI任务不存在", HTTPStatus.NOT_FOUND)
ErrFunctionCaseGenerateTaskRunNotFound = AppError(
    3110, "功能测试AI任务运行记录不存在", HTTPStatus.NOT_FOUND
)
ErrFunctionTestSuiteNotFound = AppError(3201, "功能测试集不存在", HTTPStatus.NOT_FOUND)
ErrFunctionTestSuiteNameAlreadyUse = AppError(3202, "该功能测试集名称已存在", HTTPStatus.CONFLICT)
ErrFunctionTestCaseNotFound = AppError(3301, "功能测试用例不存在", HTTPStatus.NOT_FOUND)
ErrFunctionTestCaseTitleAlreadyUse = AppError(3302, "该功能测试用例标题已存在", HTTPStatus.CONFLICT)
ErrFunctionTestCaseImportInvalid = AppError(
    3303, "功能测试用例导入内容不合法", HTTPStatus.BAD_REQUEST
)
ErrFunctionTestCaseImportFileRequired = AppError(3304, "请上传JSON文件", HTTPStatus.BAD_REQUEST)
ErrIntegrationConnectionNotFound = AppError(3401, "集成连接不存在", HTTPStatus.NOT_FOUND)
ErrIntegrationConnectionNameAlreadyUse = AppError(3402, "该集成连接名称已存在", HTTPStatus.CONFLICT)
ErrIntegrationConnectionAuthFailed = AppError(3403, "集成连接鉴权失败", HTTPStatus.BAD_REQUEST)
ErrIntegrationProviderNotSupported = AppError(
    3404, "当前集成 provider 暂不支持", HTTPStatus.BAD_REQUEST
)
ErrGitLabRemoteResourceUnavailable = AppError(3405, "GitLab 远端资源不可用", HTTPStatus.BAD_REQUEST)
ErrResourceBindingNotFound = AppError(3501, "资源绑定不存在", HTTPStatus.NOT_FOUND)
ErrResourceBindingAlreadyExists = AppError(3502, "该本地资源已存在有效绑定", HTTPStatus.CONFLICT)
ErrRemoteResourceAlreadyBound = AppError(3503, "该远端资源已被绑定", HTTPStatus.CONFLICT)
ErrResourceBindingInvalid = AppError(3504, "资源绑定关系不合法", HTTPStatus.BAD_REQUEST)
ErrZentaoRemoteResourceUnavailable = AppError(3505, "禅道远端资源不可用", HTTPStatus.BAD_REQUEST)
ErrGroupBindingInUse = AppError(3506, "仍有需求代码绑定引用该群组", HTTPStatus.CONFLICT)
ErrTestOrderNotFound = AppError(3601, "测试单不存在", HTTPStatus.NOT_FOUND)
ErrTestOrderNameAlreadyUse = AppError(3602, "该迭代下已存在同名测试单", HTTPStatus.CONFLICT)
ErrTestOrderEntryNotFound = AppError(3603, "执行条目不存在", HTTPStatus.NOT_FOUND)
ErrTestOrderCaseMismatch = AppError(3604, "用例与测试单不属于同一项目", HTTPStatus.BAD_REQUEST)
ErrTestOrderEntryDuplicate = AppError(3605, "该用例已在测试单中", HTTPStatus.CONFLICT)
ErrTestOrderSourceMismatch = AppError(
    3606, "来源测试单与目标测试单不属于同一项目", HTTPStatus.BAD_REQUEST
)
ErrTestOrderAssigneeInvalid = AppError(3607, "执行人不是该项目成员", HTTPStatus.BAD_REQUEST)
ErrTestOrderEntryAssigneeLocked = AppError(
    3608, "该执行条目已分配给其他执行人", HTTPStatus.FORBIDDEN
)
ErrBugNotFound = AppError(3701, "Bug 不存在", HTTPStatus.NOT_FOUND)
ErrBugTransitionInvalid = AppError(3702, "当前状态不允许该操作", HTTPStatus.BAD_REQUEST)
ErrBugRejectReasonInvalid = AppError(3703, "请选择拒绝原因", HTTPStatus.BAD_REQUEST)
ErrBugContentRequired = AppError(3704, "请填写说明", HTTPStatus.BAD_REQUEST)
ErrBugAssigneeInvalid = AppError(3705, "责任人不是该项目成员", HTTPStatus.BAD_REQUEST)
ErrBugSprintMismatch = AppError(3706, "迭代与 Bug 不属于同一项目", HTTPStatus.BAD_REQUEST)
ErrBugRequirementMismatch = AppError(3707, "需求与 Bug 不属于同一项目", HTTPStatus.BAD_REQUEST)
ErrBugSourceMismatch = AppError(3708, "执行记录与 Bug 不属于同一项目", HTTPStatus.BAD_REQUEST)
ErrBugSeverityInvalid = AppError(3709, "严重程度不合法", HTTPStatus.BAD_REQUEST)
ErrBugPriorityInvalid = AppError(3710, "优先级不合法", HTTPStatus.BAD_REQUEST)
ErrBugFileUnavailable = AppError(3711, "附件尚未上传完成，请重新上传后再提交", HTTPStatus.CONFLICT)


def app_error_payload(error: AppError, data: Any | None = None) -> dict[str, Any]:
    if data is None:
        data = {}
    return {"code": error.code, "message": error.message, "data": data}


def success_payload(data: Any | None = None) -> dict[str, Any]:
    return app_error_payload(ErrSuccess, data)


def dynamic_error(base: AppError, message: str) -> AppError:
    return AppError(base.code, message, base.http_code)


def validation_error_detail(errors: list[Mapping[str, Any]]) -> str:
    if not errors:
        return ErrBadRequest.message
    first = errors[0]
    location = ".".join(str(part) for part in first.get("loc", []))
    message = str(first.get("msg", ErrBadRequest.message))
    return f"{location}: {message}" if location else message
