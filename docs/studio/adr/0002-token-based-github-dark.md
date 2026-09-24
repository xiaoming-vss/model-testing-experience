# 通过 token 支持 GitHub Dark

2026-09-24。取代 [0001](0001-remove-dark-theme.md) 中仅保留浅色的决定。

用户确认恢复主题切换，并选择 GitHub 暗色风格。此前暗色的维护问题来自按组件重复覆盖样式；现在已有基础、表面、编辑器和图表的语义颜色 token，因此决定只切换 token 取值，以 GitHub Primer Dark 的深灰背景、蓝色链接、绿色主按钮及状态色作为暗色色盘。Ant Design 使用 darkAlgorithm 与具体颜色配置，避免将 CSS 变量传入颜色算法。

主题偏好为 light、dark、system，默认跟随系统，存储于 localStorage 的 mtx-theme-preference。共享 store 负责解析系统主题、同步其它标签页和设置 html 的 data-theme / color-scheme；入口 HTML 在应用加载前使用相同规则初始化，避免暗色首屏先闪浅色。存储不可用时仍允许当前页面切换。登录页与应用页头提供统一入口。

CodeMirror、React Flow 和图表消费同一主题；切换编辑器扩展不重建业务表单。树图导出读取当前页面的具体颜色值。独立 HTML 报告和品牌图形继续保留自身配色。新增样式只消费 token，暗色文件仅定义颜色变量，不恢复 dark-polish 或针对 feature 类名的补丁。旧列表规则改用等权重的 :root:root，使两种主题共享布局和样式规则。

代价是 Ant Design 算法输入仍需维护一组具体颜色，与 CSS 色盘同步核对；新增颜色角色必须提供暗色映射，并运行 check:theme、相关测试和浏览器视觉验证。主题状态测试覆盖系统变化、持久化、跨标签页同步、存储异常与首屏规则一致性。

配色参考：[GitHub Primer theme reference](https://primer.style/product/getting-started/react/theme-reference/)。
