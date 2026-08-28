import { mount } from '@vue/test-utils'
import TagPicker from './TagPicker.vue'

describe('TagPicker', () => {
  it('selects existing grouped tags without free typing', async () => {
    const wrapper = mount(TagPicker, {
      props: {
        modelValue: [],
        tagCounts: { happy: 31, 'emotion:happy': 12, sleep: 8 },
      },
    })
    const happyButton = wrapper.findAll('button.tag').find((button) => button.text().includes('开心'))
    expect(happyButton).toBeTruthy()
    await happyButton!.trigger('click')
    expect(wrapper.emitted('update:modelValue')?.[0]).toEqual([['emotion:happy']])
  })

  it('only exposes custom tag creation when explicitly enabled', () => {
    const defaultPicker = mount(TagPicker, { props: { modelValue: [], tagCounts: {} } })
    const createPicker = mount(TagPicker, { props: { modelValue: [], tagCounts: {}, allowCreate: true } })
    expect(defaultPicker.find('#custom-tag-input').exists()).toBe(false)
    expect(createPicker.find('#custom-tag-input').exists()).toBe(true)
  })

  it('searches labels and aliases instead of requiring stable keys', async () => {
    const wrapper = mount(TagPicker, {
      props: {
        modelValue: [],
        tagCounts: { 'emotion:happy': 12 },
        definitions: [{
          tag: 'emotion:happy', facet: 'emotion', label: '开心', description: '轻松、庆祝或愉快', managed: 1, asset_count: 12,
        }],
        aliases: [{ alias: '高兴', canonical_tag: 'emotion:happy' }],
      },
    })
    await wrapper.get('input[type="search"]').setValue('高兴')
    expect(wrapper.findAll('button.tag').some((button) => button.text().includes('开心'))).toBe(true)
  })

  it('selects an existing alias instead of creating a duplicate free tag', async () => {
    const wrapper = mount(TagPicker, {
      props: {
        modelValue: [],
        tagCounts: { 'emotion:happy': 12 },
        definitions: [{
          tag: 'emotion:happy', facet: 'emotion', label: '开心', description: '', managed: 1, asset_count: 12,
        }],
        aliases: [{ alias: '高兴', canonical_tag: 'emotion:happy' }],
        allowCreate: true,
      },
    })
    await wrapper.get('#custom-tag-input').setValue('高兴')
    await wrapper.get('.custom-tag button[type="submit"]').trigger('submit')
    expect(wrapper.emitted('update:modelValue')?.at(-1)).toEqual([['emotion:happy']])
  })

  it('requires a second confirmation before creating a new free tag', async () => {
    const wrapper = mount(TagPicker, {
      props: { modelValue: [], tagCounts: {}, allowCreate: true },
    })
    await wrapper.get('#custom-tag-input').setValue('party-time')
    const form = wrapper.get('form.custom-tag')
    await form.trigger('submit')
    expect(wrapper.emitted('update:modelValue')).toBeUndefined()
    expect(wrapper.text()).toContain('只作为普通图片标签保留')
    await form.trigger('submit')
    expect(wrapper.emitted('update:modelValue')?.at(-1)).toEqual([['party-time']])
  })

  it('hides role, intensity, and safety tags from user selection', () => {
    const wrapper = mount(TagPicker, {
      props: {
        modelValue: [],
        tagCounts: {
          'emotion:happy': 12,
          'role:plana': 8,
          'intensity:3': 6,
          'safety:safe': 20,
        },
      },
    })
    expect(wrapper.text()).toContain('开心')
    expect(wrapper.text()).not.toContain('plana')
    expect(wrapper.text()).not.toContain('safety:safe')
    expect(wrapper.findAll('button.tag')).toHaveLength(1)
  })

  it('preserves hidden system tags when changing a visible tag', async () => {
    const wrapper = mount(TagPicker, {
      props: {
        modelValue: ['safety:safe', 'role:plana', 'emotion:happy'],
        tagCounts: { 'emotion:happy': 12, 'emotion:calm': 4, 'safety:safe': 20 },
      },
    })
    expect(wrapper.text()).toContain('已选 1 个')
    expect(wrapper.text()).not.toContain('safety:safe')
    const calmButton = wrapper.findAll('button.tag').find((button) => button.text().includes('平静'))
    await calmButton!.trigger('click')
    expect(wrapper.emitted('update:modelValue')?.at(-1)).toEqual([
      ['safety:safe', 'role:plana', 'emotion:happy', 'emotion:calm'],
    ])
  })
})
