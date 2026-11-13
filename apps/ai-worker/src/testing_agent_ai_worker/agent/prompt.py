"""Shared prompt helpers for every execution backend."""

STRUCTURED_REQUIREMENT_INPUT_INSTRUCTION = (
    "上游若为 readable_requirement_material 0.2 JSON，请读取 functions 中各章节及待确认问题，"
    "通过 materialBlockIds 查找 materialBlocks 的来源及定位；区分已确认、未确认、冲突和示例，"
    "不得将示例、历史规则或未经确认的内容当成产品事实。"
    "用户已回答的问题必须先回写相关业务内容，再从 questions/openQuestions 删除已解决问题；保留尚未答复的问题。"
    "同一规则经多个入口引用仍是一条规则，不重复生成测试点。"
)

FUNCTIONAL_ANALYSIS_JSON_ONLY_INSTRUCTION = (
    "以审核通过的材料整理 JSON 为唯一事实依据，读取 functions、materialBlocks 和 questions；"
    "区分已确认、未确认、冲突及示例。新增业务答复需先纳入材料整理并审核。"
    "请直接返回符合 测试范围风险分析 skill 要求的测试范围风险分析 JSON，"
    "不要返回详细测试用例、cases/testCases、meta/config 包装结构，"
    "输出必须是且只能是一个可由 JSON.parse 直接解析的合法 JSON 对象："
    "第一个字符必须是 {，最后一个字符必须是 }；"
    "不得在对象前后输出空行、解释、标题、注释、Markdown 代码块或第二个 JSON 对象。"
)
FUNCTIONAL_CASE_NAMES_JSON_ONLY_INSTRUCTION = STRUCTURED_REQUIREMENT_INPUT_INSTRUCTION + (
    "请直接返回符合 测试点生成 skill 要求的测试用例名称 JSON，"
    "不要返回详细测试步骤、cases/testCases、meta/config 包装结构，"
    "不要返回 Markdown 代码块、解释文字或其他说明。"
)
FUNCTIONAL_DETAILED_CASES_JSON_ONLY_INSTRUCTION = STRUCTURED_REQUIREMENT_INPUT_INSTRUCTION + (
    "关键依据不足时，先返回以 CLARIFICATION_REQUIRED: 开头的简短澄清问题，"
    "注明受影响测试点和阻塞的操作或判定，不虚构控件、选项、路径或预期，"
    "不以 cases:[] 隐藏受阻测试点；该响应用于失败提示，不是正式阶段产物。"
    "依据齐备时，请直接返回包含 cases 数组的详细测试用例 JSON。"
    "正式输出必须是且只能是一个可由 JSON.parse 直接解析的合法 JSON 对象："
    "第一个字符必须是 {，最后一个字符必须是 }；"
    "不得在对象前后输出空行、解释、标题、注释、Markdown 代码块或第二个 JSON 对象。"
)
FUNCTIONAL_RELATION_JSON_ONLY_INSTRUCTION = (
    "请直接返回符合 mtx-analyze-test-case-relations skill 要求的用例关系 JSON（关系输出协议 2.0）。"
    "顶层只包含 schema_version、main_paths、edges；"
    "输出必须是且只能是一个可由 JSON.parse 直接解析的合法 JSON 对象："
    "第一个字符必须是 {，最后一个字符必须是 }；"
    "不得在对象前后输出空行、解释、澄清提问、标题、注释、Markdown 代码块或第二个 JSON 对象。"
)
TEST_ORDER_GRAPH_JSON_ONLY_INSTRUCTION = STRUCTURED_REQUIREMENT_INPUT_INSTRUCTION + (
    "请直接返回符合 update-test-case-graph skill 要求的完整累计图谱 JSON（关系输出协议 2.0）。"
    "顶层只包含 schema_version、main_paths、edges；"
    "输出必须是且只能是一个可由 JSON.parse 直接解析的合法 JSON 对象："
    "第一个字符必须是 {，最后一个字符必须是 }；"
    "不得在对象前后输出空行、解释、澄清提问、标题、注释、Markdown 代码块或第二个 JSON 对象。"
)
API_EXTRACTOR_JSON_ONLY_INSTRUCTION = (
    "请直接返回符合 openapi-test-config-extractor skill 要求的接口配置 JSON，"
    "不要返回测试用例、meta/config/testCases 结构，"
    "不要返回 Markdown 代码块、解释文字或其他说明。"
)
API_GENERATOR_YAML_ONLY_INSTRUCTION = (
    "请直接返回符合 api-cases-yaml-generator skill 要求的 YAML 内容，"
    "不要返回 JSON、meta/config/testCases 结构，"
    "不要返回 Markdown 代码块、解释文字或其他说明。"
)


def append_stage_instruction(extra_instruction: str, stage_instruction: str) -> str:
    """按 API 链路约定拼接平台附加约束和阶段输出约束。"""

    if extra_instruction.strip():
        return "\n\n".join([extra_instruction.strip(), stage_instruction])
    return stage_instruction


def build_skill_message(*, skill_name: str, body_text: str, extra_instruction: str) -> str:
    """按“显式 skill 名称 + 正文 + 附加约束”的约定拼 prompt。"""

    parts = [
        f"请先加载本地 skill：{skill_name}，并严格遵循该 SKILL.md 的全部规则。",
        body_text.strip(),
    ]
    if extra_instruction.strip():
        parts.append(extra_instruction.strip())
    return "\n\n".join(part for part in parts if part)
