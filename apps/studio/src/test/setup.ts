import '@testing-library/jest-dom/vitest'

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}

Object.defineProperty(globalThis, 'ResizeObserver', {
  configurable: true,
  value: ResizeObserverStub,
})

Object.defineProperty(window, 'matchMedia', {
  configurable: true,
  value: (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => undefined,
    removeListener: () => undefined,
    addEventListener: () => undefined,
    removeEventListener: () => undefined,
    dispatchEvent: () => false,
  }),
})

Object.defineProperty(window, 'scrollTo', {
  configurable: true,
  value: () => undefined,
})

const realGetComputedStyle = window.getComputedStyle.bind(window)
let computedStyleCache = new WeakMap<Element, CSSStyleDeclaration>()

/**
 * 按元素缓存 getComputedStyle，并且一旦 DOM 变动就整体作废。
 *
 * 为什么需要：jsdom 每次调用都会遍历文档里全部样式表重算级联，而 antd v5 的 cssinjs 在运行时
 * 注入数十万字符规则（实测 50 个 style 标签、约 45 万字符），单次调用约 5 秒。getByRole /
 * findByRole（可见性判定）与 user-event 的 click（pointer-events 判定）内部会反复读取同一批
 * 元素，于是每次查询或点击都要几秒，整套测试因此要跑近半小时。
 *
 * 为什么要作废：jsdom 返回的是调用那一刻的计算结果快照。antd 靠切 class 来显隐（例如打开弹框），
 * 若缓存不随 DOM 变动失效，后续查询会读到"弹框还隐藏着"的过期结果，表现为找不到 dialog / 按钮。
 * 属性、子节点与文本变动都覆盖；样式表注入（cssinjs 插 style 标签）同样是 DOM 变动。
 */
new MutationObserver(() => {
  computedStyleCache = new WeakMap()
}).observe(document, { subtree: true, childList: true, attributes: true, characterData: true })

Object.defineProperty(window, 'getComputedStyle', {
  configurable: true,
  value: (element: Element) => {
    const cached = computedStyleCache.get(element)
    if (cached) return cached
    const computed = realGetComputedStyle(element)
    computedStyleCache.set(element, computed)
    return computed
  },
})

const emptyRect = {
  x: 0,
  y: 0,
  width: 0,
  height: 0,
  top: 0,
  right: 0,
  bottom: 0,
  left: 0,
  toJSON: () => ({}),
}

Range.prototype.getBoundingClientRect = () => emptyRect
Range.prototype.getClientRects = () => ({
  length: 0,
  item: () => null,
  [Symbol.iterator]: function* iterator() {},
}) as DOMRectList
