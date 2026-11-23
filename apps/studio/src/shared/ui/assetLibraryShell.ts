/** 资产库页签外壳：资产库页与接口详情页共用同一套高度链。 */
export const ASSET_LIBRARY_PAGE_CLASS =
  'workbench-page asset-library-page flex min-h-0 min-w-0 flex-1 flex-col'

export const ASSET_LIBRARY_TAB_PANEL_CLASS =
  'asset-library-tab-panel flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden'

/* 页签页根保留自己的页面内距：用例库由 .api-automation-content 提供，
   接口库/接口详情由 interfacePageRootClass 提供。这里不能再把子页 padding 清零。 */
export const ASSET_LIBRARY_TAB_PANE_CLASS =
  'asset-library-tab-pane flex min-h-0 min-w-0 flex-1 flex-col [&[hidden]]:hidden [&>.workbench-page]:min-h-0 [&>.workbench-page]:flex-auto'
