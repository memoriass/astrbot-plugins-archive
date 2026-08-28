import { vi } from 'vitest'

const mocks = vi.hoisted(() => ({ assets: vi.fn(), status: vi.fn() }))

vi.mock('../api', () => ({
  galleryApi: { assets: mocks.assets, status: mocks.status },
}))

import { useAssetBrowser } from './useAssetBrowser'

describe('useAssetBrowser', () => {
  it('clears page-local selection after every reload', async () => {
    mocks.status.mockResolvedValue({ assets: 2, review_assets: 0, tags: 0, tag_counts: {}, tag_list: [], fts_available: true, definitions: [] })
    mocks.assets.mockResolvedValue({
      assets: [{ id: 1, tags: [], title: '', caption: '', asset_ref: 'gallery:1', sha256: '', file_path: '', original_path: '', mime_type: 'image/png', source: '', created_at: 1, updated_at: 1 }],
      total: 1,
      page: 1,
      page_size: 48,
      page_count: 1,
      sources: [],
    })
    const browser = useAssetBrowser()
    await browser.initialize()
    browser.toggleSelection(1)
    expect(browser.selection.value.size).toBe(1)
    await browser.loadAssets()
    expect(browser.selection.value.size).toBe(0)
  })
})
