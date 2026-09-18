export function normalizeText(value?: string | null) {
  return value ?? ''
}

export function setValueIfChanged<T extends object, K extends keyof T>(
  payload: Partial<T>,
  key: K,
  currentValue: T[K],
  nextValue: T[K],
) {
  if (currentValue !== nextValue) {
    payload[key] = nextValue
  }
}

export function setDefinedValueIfChanged<T extends object, K extends keyof T>(
  payload: Partial<T>,
  key: K,
  currentValue: T[K] | undefined,
  nextValue: T[K] | undefined,
) {
  if (nextValue !== undefined && currentValue !== nextValue) {
    payload[key] = nextValue
  }
}

export function setBooleanIfChanged<T extends object, K extends keyof T>(
  payload: Partial<T>,
  key: K,
  currentValue: boolean | undefined | null,
  nextValue: boolean | undefined | null,
) {
  if (Boolean(currentValue) !== Boolean(nextValue)) {
    payload[key] = Boolean(nextValue) as T[K]
  }
}

export function setNormalizedTextIfChanged<T extends object, K extends keyof T>(
  payload: Partial<T>,
  key: K,
  currentValue: string | undefined | null,
  nextValue: string | undefined | null,
) {
  if (normalizeText(currentValue) !== normalizeText(nextValue)) {
    payload[key] = (nextValue ?? '') as T[K]
  }
}
