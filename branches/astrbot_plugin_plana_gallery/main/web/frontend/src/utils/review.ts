export function clampActiveIndex(current: number, assetCount: number) {
  if (assetCount <= 0) return -1
  return Math.min(Math.max(current, 0), assetCount - 1)
}
