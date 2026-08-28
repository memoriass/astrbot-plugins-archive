<script setup lang="ts">
import { ref } from 'vue'
import type { GalleryAsset } from '../types'
import { galleryApi } from '../api'
import { tagLabel } from '../utils/tags'

defineProps<{
  assets: GalleryAsset[]
  selectedIds: Set<number>
  loading: boolean
  emptyText?: string
  density?: 'comfortable' | 'compact'
  activeId?: number | null
}>()
const emit = defineEmits<{ select: [id: number]; open: [asset: GalleryAsset] }>()
const loadedIds = ref(new Set<number>())
const failedIds = ref(new Set<number>())
const thumbnailNonce = ref<Record<number, number>>({})

function markLoaded(id: number) {
  loadedIds.value = new Set(loadedIds.value).add(id)
  const next = new Set(failedIds.value)
  next.delete(id)
  failedIds.value = next
}

function markFailed(id: number) {
  failedIds.value = new Set(failedIds.value).add(id)
}

function thumbnailUrl(asset: GalleryAsset, density: 'comfortable' | 'compact' | undefined) {
  const base = galleryApi.thumbnailUrl(asset.id, density === 'compact' ? 320 : 640)
  return `${base}&v=${thumbnailNonce.value[asset.id] || asset.updated_at}`
}

async function rebuild(asset: GalleryAsset) {
  await galleryApi.rebuildThumbnail(asset.id, 320)
  const next = new Set(failedIds.value)
  next.delete(asset.id)
  failedIds.value = next
  thumbnailNonce.value = { ...thumbnailNonce.value, [asset.id]: Date.now() }
}
</script>

<template>
  <div class="asset-grid" :class="`density-${density || 'comfortable'}`" :aria-busy="loading">
    <article
      v-for="asset in assets"
      :key="asset.id"
      class="asset-card"
      :class="{ selected: selectedIds.has(asset.id), active: activeId === asset.id }"
      :data-asset-id="asset.id"
    >
      <button type="button" class="asset-card__image" :aria-label="`查看 ${asset.title || asset.asset_ref}`" @click="emit('open', asset)">
        <span v-if="!loadedIds.has(asset.id) && !failedIds.has(asset.id)" class="thumbnail-skeleton" aria-hidden="true" />
        <img v-if="asset.file_valid !== false && !failedIds.has(asset.id)" :src="thumbnailUrl(asset, density)" :alt="asset.caption || asset.title || ''" loading="lazy" decoding="async" @load="markLoaded(asset.id)" @error="markFailed(asset.id)" />
        <span v-else class="thumbnail-fallback">{{ asset.file_valid === false ? '原图已失效' : '缩略图不可用' }}</span>
      </button>
      <button v-if="asset.file_valid !== false && failedIds.has(asset.id)" type="button" class="thumbnail-retry" @click.stop="rebuild(asset)">重新生成</button>
      <label class="asset-card__select">
        <input type="checkbox" :checked="selectedIds.has(asset.id)" :aria-label="`选择 ${asset.title || asset.asset_ref}`" @change="emit('select', asset.id)" />
      </label>
      <div class="asset-card__body">
        <button type="button" class="asset-card__title" @click="emit('open', asset)">{{ asset.title || `图片 #${asset.id}` }}</button>
        <p>{{ asset.caption || '暂无图片说明' }}</p>
        <div class="asset-card__tags">
          <span v-for="tag in asset.tags.slice(0, 4)" :key="tag" class="mini-tag">{{ tagLabel(tag) }}</span>
          <span v-if="asset.tags.length > 4" class="mini-tag muted">+{{ asset.tags.length - 4 }}</span>
        </div>
      </div>
      <div class="asset-card__meta">
        <span>{{ asset.source || '本地导入' }}</span>
        <span :class="asset.file_valid === false || asset.tags.includes('needs-review') ? 'status pending' : 'status ready'">{{ asset.file_valid === false ? '文件失效' : asset.tags.includes('needs-review') ? '待审核' : '可使用' }}</span>
      </div>
    </article>
    <div v-if="loading" class="grid-state" role="status">正在加载图库…</div>
    <div v-else-if="!assets.length" class="grid-state">
      <strong>没有符合条件的图片</strong>
      <p>{{ emptyText || '尝试减少标签条件或清空搜索关键词。' }}</p>
    </div>
  </div>
</template>
