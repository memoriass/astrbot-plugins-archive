import { mount } from '@vue/test-utils'
import PaginationBar from './PaginationBar.vue'

describe('PaginationBar', () => {
  it('emits bounded page navigation', async () => {
    const wrapper = mount(PaginationBar, { props: { page: 3, pageCount: 8, total: 396, pageSize: 48 } })
    await wrapper.get('button[aria-label="上一页"]').trigger('click')
    await wrapper.get('button[aria-label="下一页"]').trigger('click')
    expect(wrapper.emitted('page')).toEqual([[2], [4]])
  })

  it('announces the current page', () => {
    const wrapper = mount(PaginationBar, { props: { page: 2, pageCount: 4, total: 100, pageSize: 24 } })
    expect(wrapper.get('[aria-current="page"]').text()).toBe('2')
  })
})
