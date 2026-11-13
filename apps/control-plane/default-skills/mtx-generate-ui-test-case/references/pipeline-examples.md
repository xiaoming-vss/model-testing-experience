# 三个场景的一条完整交接链

这些是虚构的格式与方法样例，不表示已执行真实业务系统。三条正式用例分别演示普通文字断言、可补全定位缺口和运行时输入值捕获。[执行上下文](../examples/pipeline/context.json) 声明环境 baseUrl、/demo 入口和无需登录；每条 YAML 自行打开页面，不依赖上一条的页面或会话。外部报表控件的内部实现故意未提供，不能将第二条草稿当作可直接运行的测试。

本阶段的输入与输出文件在 [examples/pipeline](../examples/pipeline)。先读 [源码](../examples/pipeline/source/page.html) 和 [正式用例](../examples/pipeline/formal-cases.json)，再查看 [元素清单](../examples/pipeline/surface.json)。UI 各阶段的正式输出字段均保持原契约；源码定位候选不冒充运行时确认。

- U1：帮助按钮及文本可从源码定位；设计保留点击和文字断言。
- U2：业务预期“已完成”明确，外部组件内部 DOM 未知；场景仍 included，YAML 仅将未知定位声明为 missingFields，不削弱预期。
- U3：输入新备注后通过 saveTo.source=value 获取实际实时值，再与独立的新备注比较；采集本身不等于验证相等。

本阶段包含 [完整设计](../examples/pipeline/design.json)，每个原始动作和预期都有逐字来源。缺少定位并未导致 U2 被排除。

后续文件为 [结构化候选](../examples/pipeline/candidate.json)、[单一 audit](../examples/pipeline/audit.json) 和 [可读 YAML](../examples/pipeline/cases.yaml)。audit 是方法示例与字段对应说明，不是独立审查或真实运行证据。U1 使用 basic，U2 的缺口及 U3 的运行时值使用 detailed。

从 skill 目录执行，输出写到临时路径，避免覆盖示例：

```bash
python3 scripts/export_ui_case.py --candidate examples/pipeline/candidate.json --design examples/pipeline/design.json --audit examples/pipeline/audit.json --output /tmp/ui-pipeline-example.yaml
```

导出允许第二条的真实定位缺口；正式导入前必须补全。若 included 目标实际依赖不支持的循环等能力，应记录 design_dependency 并停止成功导出，而不是用 missingFields 掩盖。例子的语义证明仍需结合实际源码和执行上下文重新建立。
