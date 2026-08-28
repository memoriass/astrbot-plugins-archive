<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { galleryApi } from '../api'
import { useAssetBrowser } from '../composables/useAssetBrowser'
import type { GalleryAsset } from '../types'
import AssetDrawer from '../components/AssetDrawer.vue'
import AssetGrid from '../components/AssetGrid.vue'
import BulkTagDialog from '../components/BulkTagDialog.vue'
import ConfirmDialog from '../components/ConfirmDialog.vue'
import FilterBoard from '../components/FilterBoard.vue'
import ImportDialog from '../components/ImportDialog.vue'
import PaginationBar from '../components/PaginationBar.vue'

const browser = useAssetBrowser('all')
const detail = ref<GalleryAsset | null>(null)
const bulkOpen = ref(false)
const importOpen = ref(false)
const density = ref<'comfortable' | 'compact'>('comfortable')
const confirmAction = ref<'delete' | 'approve' | null>(null)
const actionBusy = ref(false)
const actionError = ref('')

onMounted(browser.initialize)

async function resetFilters() {
  Object.assign(browser.filters, { query: '', tags: [], excludeTags: [], tagMode: 'all', review: 'all', source: '', sort: 'updated_desc', page: 1 })
  await browser.loadAssets()
}

async function changePage(page: number) {
  browser.filters.page = page
  await browser.loadAssets()
  window.scrollTo({ top: 0, behavior: 'smooth' })
}

async function applyBulk(payload: { addTags: string[]; removeTags: string[]; approve: boolean }) {
  await galleryApi.batchTags([...browser.selection.value], payload.addTags, payload.removeTags, payload.approve)
  bulkOpen.value = false
  browser.clearSelection()
  await Promise.all([browser.loadAssets(), browser.loadStatus()])
}

async function runConfirmedAction() {
  const ids = [...browser.selection.value]
  if (!ids.length || !confirmAction.value) return
  actionBusy.value = true
  actionError.value = ''
  try {
    if (confirmAction.value === 'delete') await galleryApi.batchDelete(ids)
    else await galleryApi.batchTags(ids, [], [], true)
    confirmAction.value = null
    browser.clearSelection()
    await browser.initialize()
  } catch (reason) {
    actionError.value = reason instanceof Error ? reason.message : '操作失败'
  } finally {
    actionBusy.value = false
  }
}
</script>

<template>
  <div class="view-page">
    <header class="page-header library-header">
      <div><h1>资产整理</h1><p>浏览、筛选、批量打标和管理本地图片。</p></div>
      <button type="button" class="button primary" @click="importOpen = true">导入图片</button>
    </header>
    <section class="metrics" aria-label="图库概况">
      <article><span>全部图片</span><strong>{{ browser.status.value?.assets ?? '—' }}</strong></article>
      <article><span>当前结果</span><strong>{{ browser.total.value }}</strong></article>
      <article><span>待审核</span><strong>{{ browser.status.value?.review_assets ?? '—' }}</strong></article>
      <article><span>原有标签</span><strong>{{ browser.status.value?.tags ?? '—' }}</strong></article>
    </section>
    <div class="search-strip">
      <label for="library-search">快速搜索</label>
      <input id="library-search" v-model="browser.filters.query" type="search" placeholder="搜索标题、说明、asset_ref 或标签" @keyup.enter="browser.applyFilters" />
      <select v-model="browser.filters.sort" aria-label="排序方式" @change="browser.applyFilters">
        <option value="updated_desc">最近更新</option><option value="created_desc">最新入库</option><option value="created_asc">最早入库</option><option value="title_asc">标题 A–Z</option>
      </select>
      <button type="button" class="button secondary" @click="browser.applyFilters">搜索</button>
    </div>
    <FilterBoard v-if="browser.status.value" :filters="browser.filters" :tag-counts="browser.status.value.tag_counts" :sources="browser.sources.value" @apply="browser.applyFilters" @reset="resetFilters" />
    <div class="result-toolbar">
      <div><strong>{{ browser.total.value }} 张图片</strong><span>第 {{ browser.filters.page }} / {{ browser.pageCount.value }} 页</span></div>
      <div class="toolbar-actions">
        <div class="density-toggle" role="group" aria-label="网格密度">
          <button type="button" :aria-pressed="density === 'comfortable'" @click="density = 'comfortable'">舒适</button>
          <button type="button" :aria-pressed="density === 'compact'" @click="density = 'compact'">紧凑</button>
        </div>
        <button type="button" class="button ghost" :disabled="!browser.assets.value.length" @click="browser.selectPage">选择本页</button>
        <button v-if="browser.selection.value.size" type="button" class="button secondary" @click="confirmAction = 'approve'">确认通过</button>
        <button v-if="browser.selection.value.size" type="button" class="button danger ghost-danger" @click="confirmAction = 'delete'">批量删除</button>
        <button v-if="browser.selection.value.size" type="button" class="button primary" @click="bulkOpen = true">整理已选 {{ browser.selection.value.size }} 张</button>
      </div>
    </div>
    <p v-if="actionError" class="page-error" role="alert">{{ actionError }}</p>
    <p v-if="browser.error.value" class="page-error" role="alert">加载失败：{{ browser.error.value }}</p>
    <AssetGrid :assets="browser.assets.value" :selected-ids="browser.selection.value" :loading="browser.loading.value" :density="density" @select="browser.toggleSelection" @open="detail = $event" />
    <PaginationBar :page="browser.filters.page" :page-count="browser.pageCount.value" :total="browser.total.value" :page-size="browser.filters.pageSize" @page="changePage" @page-size="browser.filters.pageSize = $event; changePage(1)" />
    <AssetDrawer :asset="detail" :tag-counts="browser.status.value?.tag_counts || {}" :definitions="browser.status.value?.definitions || []" :aliases="browser.status.value?.aliases || []" @close="detail = null" @saved="browser.initialize" @deleted="browser.initialize" />
    <BulkTagDialog :open="bulkOpen" :count="browser.selection.value.size" :tag-counts="browser.status.value?.tag_counts || {}" :definitions="browser.status.value?.definitions || []" :aliases="browser.status.value?.aliases || []" @close="bulkOpen = false" @apply="applyBulk" />
    <ImportDialog :open="importOpen" :tag-counts="browser.status.value?.tag_counts || {}" :definitions="browser.status.value?.definitions || []" :aliases="browser.status.value?.aliases || []" @close="importOpen = false" @imported="browser.initialize" />
    <ConfirmDialog
      :open="Boolean(confirmAction)"
      :title="confirmAction === 'delete' ? `删除已选 ${browser.selection.value.size} 张图片？` : `确认通过已选 ${browser.selection.value.size} 张图片？`"
      :description="confirmAction === 'delete' ? '删除会移除本地原图和缩略图，但会保留 tombstone。此操作不可撤销。' : '确认后图片将移除 needs-review，并进入安全检索候选；标签内容不会被自动改写。'"
      :confirm-label="confirmAction === 'delete' ? '确认删除' : '确认通过'"
      :danger="confirmAction === 'delete'"
      :busy="actionBusy"
      @close="confirmAction = null"
      @confirm="runConfirmedAction"
    />
  </div>
</template>
