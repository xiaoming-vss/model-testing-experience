export type OrderNoItem = { orderNo?: number | null }

export function orderNoOrMax(value?: number | null) {
  return value ?? Number.MAX_SAFE_INTEGER
}

export function compareByOrderNo(left: OrderNoItem, right: OrderNoItem) {
  return orderNoOrMax(left.orderNo) - orderNoOrMax(right.orderNo)
}
