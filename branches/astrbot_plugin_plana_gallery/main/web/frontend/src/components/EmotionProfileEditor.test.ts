import { defineComponent, ref } from 'vue'
import { mount } from '@vue/test-utils'
import EmotionProfileEditor from './EmotionProfileEditor.vue'
import type { EmotionProfile } from '../types'

const definitions = [
  { tag: 'emotion:excited', facet: 'emotion', label: '兴奋', description: '期待与激动', managed: 1, asset_count: 3 },
  { tag: 'emotion:speechless', facet: 'emotion', label: '无语', description: '无奈或不知道如何回应', managed: 1, asset_count: 2 },
]

const Harness = defineComponent({
  components: { EmotionProfileEditor },
  setup() {
    const tags = ref(['emotion:excited', 'emotion:speechless'])
    const emotions = ref<EmotionProfile[]>([])
    return { definitions, emotions, tags }
  },
  template: '<EmotionProfileEditor v-model="emotions" :tags="tags" :definitions="definitions" />',
})

describe('EmotionProfileEditor', () => {
  it('maintains multiple emotions with one primary and individual intensities', async () => {
    const wrapper = mount(Harness)
    await wrapper.vm.$nextTick()

    const rows = wrapper.findAll('.emotion-editor__row')
    expect(rows).toHaveLength(2)
    expect(rows[0].text()).toContain('兴奋')
    expect(rows[1].text()).toContain('无语')

    await rows[0].findAll('.intensity-control button')[2].trigger('click')
    await rows[1].findAll('.intensity-control button')[0].trigger('click')
    await rows[1].get('.emotion-primary').trigger('click')

    const profiles = wrapper.vm.emotions as EmotionProfile[]
    expect(profiles).toEqual([
      expect.objectContaining({ emotion_tag: 'emotion:excited', intensity: 3, prominence: 'secondary' }),
      expect.objectContaining({ emotion_tag: 'emotion:speechless', intensity: 1, prominence: 'primary' }),
    ])
    expect(profiles.filter((item) => item.prominence === 'primary')).toHaveLength(1)
    expect(rows[0].text()).toContain('激动欢呼')
  })

  it('warns about multiple strong and opposing emotions without blocking edits', async () => {
    const wrapper = mount(EmotionProfileEditor, {
      props: {
        modelValue: [
          { emotion_tag: 'emotion:excited', intensity: 3, prominence: 'primary' },
          { emotion_tag: 'emotion:angry', intensity: 3, prominence: 'secondary' },
        ],
        tags: ['emotion:excited', 'emotion:angry'],
        definitions,
      },
    })
    expect(wrapper.get('.emotion-editor__warnings').text()).toContain('多个强烈情绪')
    expect(wrapper.get('.emotion-editor__warnings').text()).toContain('正向与负向情绪并存')
    expect(wrapper.findAll('.intensity-control')).toHaveLength(2)
  })

  it('removes the profile when its emotion tag is removed', async () => {
    const wrapper = mount(Harness)
    await wrapper.vm.$nextTick()
    wrapper.vm.tags = ['emotion:excited']
    await wrapper.vm.$nextTick()

    expect(wrapper.vm.emotions).toEqual([
      expect.objectContaining({ emotion_tag: 'emotion:excited', prominence: 'primary' }),
    ])
  })
})
