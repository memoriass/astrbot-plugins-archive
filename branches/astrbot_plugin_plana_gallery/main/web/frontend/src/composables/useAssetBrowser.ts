import { computed, reactive, ref } from 'vue'
import { galleryApi } from '../api'
import type { AssetFilters, GalleryAsset, GalleryStatus } from '../types'

export function useAssetBrowser(defaultReview: AssetFilters['review'] = 'all') {
  const filters = reactive<AssetFilters>({
    query: '',
    tags: [],
    excludeTags: [],
    tagMode: 'all',
    review: defaultReview,
    source: '',
    sort: 'updated_desc',
    page: 1,
    pageSize: 48,
  })
  const assets = ref<GalleryAsset[]>([])
  const status = ref<GalleryStatus | null>(null)
  const sources = ref<Array<{ source: string; count: number }>>([])
  const total = ref(0)
  const pageCount = ref(1)
  const loading = ref(false)
  const error = ref('')
  const selection = ref(new Set<number>())

  const selectedAssets = computed(() => assets.value.filter((asset) => selection.value.has(asset.id)))

  async function loadStatus() {
    status.value = await galleryApi.status()
  }

  async function loadAssets() {
    loading.value = true
    error.value = ''
    try {
      const page = await galleryApi.assets(filters)
      assets.value = page.assets
      total.value = page.total
      pageCount.value = page.page_count
      sources.value = page.sources
      if (filters.page > page.page_count) filters.page = page.page_count
      selection.value = new Set()
    } catch (reason) {
      error.value = reason instanceof Error ? reason.message : '加载失败'
    } finally {
      loading.value = false
    }
  }

  async function initialize() {
    await Promise.all([loadStatus(), loadAssets()])
  }

  function applyFilters() {
    filters.page = 1
    return loadAssets()
  }

  function toggleSelection(id: number) {
    const next = new Set(selection.value)
    next.has(id) ? next.delete(id) : next.add(id)
    selection.value = next
  }

  function selectPage() {
    selection.value = new Set(assets.value.map((asset) => asset.id))
  }

  function clearSelection() {
    selection.value = new Set()
  }

  return {
    filters,
    assets,
    status,
    sources,
    total,
    pageCount,
    loading,
    error,
    selection,
    selectedAssets,
    initialize,
    loadAssets,
    loadStatus,
    applyFilters,
    toggleSelection,
    selectPage,
    clearSelection,
  }
}
