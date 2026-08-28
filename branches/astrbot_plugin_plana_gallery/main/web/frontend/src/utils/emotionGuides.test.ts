import { emotionProfileWarnings, intensityGuide } from './emotionGuides'

describe('emotion guides', () => {
  it('provides emotion-specific intensity examples', () => {
    expect(intensityGuide('emotion:speechless', 1).example).toContain('轻微无奈')
    expect(intensityGuide('emotion:speechless', 3).example).toContain('麻了')
    expect(intensityGuide('emotion:helpless', 2).example).toContain('只能接受')
    expect(intensityGuide('emotion:panicked', 3).example).toContain('失去从容')
  })

  it('flags strong opposing profiles', () => {
    expect(emotionProfileWarnings([
      { emotion_tag: 'emotion:excited', intensity: 3, prominence: 'primary' },
      { emotion_tag: 'emotion:angry', intensity: 3, prominence: 'secondary' },
    ])).toHaveLength(2)
  })
})
