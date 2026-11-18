/**
 * 接口库列表、仓库与详情共用的页面根间距。
 * 760px 以下的高度链仍由 interface-library.module.css 的 `.pageRoot` 维护，
 * 这里只承载普通间距，避免页面根容器再写一份布局规则。
 */
export const interfacePageRootClass =
  'gap-3 px-[var(--app-page-gutter)] pt-3 pb-4 max-[760px]:pt-2 max-[760px]:pb-3.5'
