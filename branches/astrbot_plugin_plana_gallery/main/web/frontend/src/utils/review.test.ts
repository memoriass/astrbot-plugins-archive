import { clampActiveIndex } from './review'

describe('clampActiveIndex', () => {
  it('uses -1 for an empty review queue', () => {
    expect(clampActiveIndex(4, 0)).toBe(-1)
  })

  it('keeps keyboard focus inside the current page', () => {
    expect(clampActiveIndex(8, 3)).toBe(2)
    expect(clampActiveIndex(-1, 3)).toBe(0)
  })
})
