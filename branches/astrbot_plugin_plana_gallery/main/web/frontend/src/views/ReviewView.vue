<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { galleryApi } from '../api'
import { useAssetBrowser } from '../composables/useAssetBrowser'
import type { EmotionProfile, GalleryAsset } from '../types'
import AssetDrawer from '../components/AssetDrawer.vue'
import AssetGrid from '../components/AssetGrid.vue'
import ConfirmDialog from '../components/ConfirmDialog.vue'
import PaginationBar from '../components/PaginationBar.vue'
import TagPicker from '../components/TagPicker.vue'
import EmotionProfileEditor from '../components/EmotionProfileEditor.vue'
import { clampActiveIndex } from '../utils/review'

const browser = useAssetBrowser('pending')
const detail = ref<GalleryAsset | null>(null)
const addTags = ref<string[]>([])
const removeTags = ref<string[]>([])
const emotionProfiles = ref<EmotionProfile[]>([])
const actionBusy = ref(false)
const actionError = ref('')
const suggestions = ref<Array<{ id: number; asset_ref: string; suggested_tags?: string[]; confidence?: number }>>([])
const acceptedSuggestions = ref<Record<number, string[]>>({})
const activeIndex = ref(-1)
const approveOpen = ref(false)
const selectedHasInvalid = computed(() => browser.selectedAssets.value.some((asset) => asset.file_valid === false))

onMounted(async () => {
  window.addEventListener('keydown', onShortcut)
  await browser.initialize()
})
onBeforeUnmount(() => window.removeEventListener('keydown', onShortcut))

async function applyTags(approve: boolean) {
  if (!browser.selection.value.size) return
  actionBusy.value = true
  actionError.value = ''
  try {
    const selected = browser.selectedAssets.value
    await galleryApi.reviewCommit(
      selected,
      acceptedSuggestions.value,
      addTags.value,
      removeTags.value,
      emotionProfiles.value,
      approve,
    )
    browser.clearSelection()
    addTags.value = []
    removeTags.value = []
    emotionProfiles.value = []
    suggestions.value = []
    acceptedSuggestions.value = {}
    approveOpen.value = false
    await browser.initialize()
  } catch (reason) {
    actionError.value = reason instanceof Error ? reason.message : '批量操作失败'
  } finally {
    actionBusy.value = false
  }
}

async function analyzeSelection() {
  if (!browser.selection.value.size) return
  actionBusy.value = true
  actionError.value = ''
  try {
    const result = await galleryApi.analyzeTags([...browser.selection.value])
    suggestions.value = result.assets || []
    acceptedSuggestions.value = {}
  } catch (reason) {
    actionError.value = reason instanceof Error ? reason.message : '生成建议失败'
  } finally {
    actionBusy.value = false
  }
}

function toggleSuggestion(assetId: number, tag: string) {
  const current = acceptedSuggestions.value[assetId] || []
  acceptedSuggestions.value = {
    ...acceptedSuggestions.value,
    [assetId]: current.includes(tag) ? current.filter((item) => item !== tag) : [...current, tag],
  }
}

function onShortcut(event: KeyboardEvent) {
  const target = event.target as HTMLElement | null
  if (target?.matches('input, textarea, select, [contenteditable="true"]')) return
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 's') {
    event.preventDefault()
    void applyTags(false)
    return
  }
  if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') {
    event.preventDefault()
    if (browser.selection.value.size) approveOpen.value = true
    return
  }
  if (!browser.assets.value.length || activeIndex.value < 0) return
  if (event.key.toLowerCase() === 'j') activeIndex.value = Math.min(activeIndex.value + 1, browser.assets.value.length - 1)
  else if (event.key.toLowerCase() === 'k') activeIndex.value = Math.max(activeIndex.value - 1, 0)
  else if (event.code === 'Space') {
    event.preventDefault()
    const active = browser.assets.value[activeIndex.value]
    if (active) browser.toggleSelection(active.id)
    return
  } else return
  event.preventDefault()
  const active = browser.assets.value[activeIndex.value]
  if (active) void nextTick(() => document.querySelector(`[data-asset-id="${active.id}"]`)?.scrollIntoView({ block: 'nearest' }))
}

watch(browser.assets, (assets) => {
  activeIndex.value = clampActiveIndex(activeIndex.value, assets.length)
})
</script>

<template>
  <div class="view-page">
    <header class="page-header review-header"><div><h1>待审核工作台</h1><p>先从现有标签中选择，再人工确认；保存标签与审核通过始终是两个动作。</p></div><button type="button" class="button secondary" @click="browser.initialize">刷新队列</button></header>
    <div class="review-guide"><strong>连续审核</strong><span>J / K 切换 · Space 选择 · Ctrl+S 仅保存 · Ctrl+Enter 确认通过</span></div>
    <div class="review-workspace">
      <section class="review-queue" aria-labelledby="review-queue-title">
        <div class="search-strip compact-strip"><label for="review-search">搜索队列</label><input id="review-search" v-model="browser.filters.query" type="search" placeholder="标题、说明或已有标签" @keyup.enter="browser.applyFilters" /><button type="button" class="button secondary" @click="browser.applyFilters">筛选</button></div>
        <div class="result-toolbar"><div><strong id="review-queue-title">待审核 {{ browser.total.value }} 张</strong><span>{{ browser.selection.value.size ? `本页已选择 ${browser.selection.value.size} 张` : '建议每批处理相似内容' }}</span></div><div class="toolbar-actions"><button type="button" class="button ghost" :disabled="!browser.assets.value.length" @click="browser.selectPage">选择本页</button><button v-if="browser.selection.value.size" type="button" class="button ghost" @click="browser.clearSelection">取消选择</button></div></div>
        <AssetGrid :assets="browser.assets.value" :selected-ids="browser.selection.value" :loading="browser.loading.value" :active-id="browser.assets.value[activeIndex]?.id" empty-text="当前没有待审核图片。新导入且未打标签的图片会出现在这里。" @select="browser.toggleSelection" @open="detail = $event" />
        <PaginationBar :page="browser.filters.page" :page-count="browser.pageCount.value" :total="browser.total.value" :page-size="browser.filters.pageSize" @page="browser.filters.page = $event; browser.loadAssets()" @page-size="browser.filters.pageSize = $event; browser.filters.page = 1; browser.loadAssets()" />
      </section>
      <aside class="review-tagging" aria-labelledby="review-tagging-title">
        <header class="review-tagging__header"><div><span>当前选择</span><h2 id="review-tagging-title">批量打标</h2></div><strong>{{ browser.selection.value.size }}</strong></header>
        <p class="review-tagging__summary">{{ browser.selection.value.size ? `已选择 ${browser.selection.value.size} 张图片，可以统一添加标签或确认通过。` : '先在左侧选择图片；打标工具会一直保留在这里。' }}</p>
        <TagPicker v-model="addTags" :tag-counts="browser.status.value?.tag_counts || {}" :definitions="browser.status.value?.definitions || []" :aliases="browser.status.value?.aliases || []" label="添加标签" allow-create compact hide-intensity />
        <EmotionProfileEditor v-model="emotionProfiles" :tags="addTags" :definitions="browser.status.value?.definitions || []" compact />
        <details class="remove-tags-panel"><summary>移除已有标签</summary><TagPicker v-model="removeTags" :tag-counts="browser.status.value?.tag_counts || {}" :definitions="browser.status.value?.definitions || []" :aliases="browser.status.value?.aliases || []" label="选择要移除的标签" compact /></details>
        <div class="review-tagging__actions">
          <button type="button" class="button secondary" :disabled="!browser.selection.value.size || actionBusy" @click="analyzeSelection">生成建议</button>
          <button type="button" class="button secondary" :disabled="!browser.selection.value.size || actionBusy" @click="applyTags(false)">仅保存标签</button>
          <button type="button" class="button primary" :disabled="!browser.selection.value.size || actionBusy || selectedHasInvalid" @click="approveOpen = true">保存并确认通过</button>
        </div>
        <p class="review-tagging__note">标签编辑不会自动审核。只有“保存并确认通过”会移除待审核状态。</p>
        <p v-if="selectedHasInvalid" class="form-error" role="alert">已选图片包含失效原图，修复文件后才能审核通过。</p>
        <p v-if="actionError" class="form-error" role="alert">{{ actionError }}</p>
        <section v-if="suggestions.length" class="suggestion-list" aria-live="polite">
          <h3>AI 建议（逐项接受）</h3>
          <article v-for="item in suggestions" :key="item.id">
            <div class="suggestion-head"><code>{{ item.asset_ref }}</code><span>{{ Math.round((item.confidence || 0) * 100) }}%</span></div>
            <div class="suggestion-tags">
              <button
                v-for="tag in item.suggested_tags || []"
                :key="tag"
                type="button"
                class="tag"
                :class="{ selected: (acceptedSuggestions[item.id] || []).includes(tag) }"
                :aria-pressed="(acceptedSuggestions[item.id] || []).includes(tag)"
                @click="toggleSuggestion(item.id, tag)"
              >{{ tag }}</button>
              <span v-if="!item.suggested_tags?.length">暂无建议</span>
            </div>
          </article>
        </section>
      </aside>
    </div>
    <AssetDrawer :asset="detail" :tag-counts="browser.status.value?.tag_counts || {}" :definitions="browser.status.value?.definitions || []" :aliases="browser.status.value?.aliases || []" @close="detail = null" @saved="browser.initialize" />
    <ConfirmDialog
      :open="approveOpen"
      :title="`保存并确认通过 ${browser.selection.value.size} 张图片？`"
      description="AI 建议只会应用已手动接受的标签；确认后才会移除 needs-review 并允许进入聊天候选。"
      confirm-label="保存并确认通过"
      :busy="actionBusy"
      @close="approveOpen = false"
      @confirm="applyTags(true)"
    />
  </div>
</template>
