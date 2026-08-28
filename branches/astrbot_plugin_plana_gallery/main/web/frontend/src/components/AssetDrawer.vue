<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'
import type { EmotionProfile, GalleryAsset, TagAlias, TagDefinition } from '../types'
import { galleryApi } from '../api'
import ConfirmDialog from './ConfirmDialog.vue'
import TagPicker from './TagPicker.vue'
import EmotionProfileEditor from './EmotionProfileEditor.vue'

const props = withDefaults(defineProps<{
  asset: GalleryAsset | null
  tagCounts: Record<string, number>
  definitions?: TagDefinition[]
  aliases?: TagAlias[]
}>(), { definitions: () => [], aliases: () => [] })
const emit = defineEmits<{ close: []; saved: []; deleted: [] }>()
const dialog = ref<HTMLDialogElement | null>(null)
const draft = ref<GalleryAsset | null>(null)
const tags = ref<string[]>([])
const emotions = ref<EmotionProfile[]>([])
const saving = ref(false)
const error = ref('')
const deleteOpen = ref(false)

watch(() => props.asset, async (asset) => {
  if (!asset) {
    dialog.value?.close()
    return
  }
  draft.value = { ...asset, tags: [...asset.tags] }
  tags.value = asset.tags.filter((tag) => !tag.startsWith('intensity:'))
  emotions.value = (asset.emotions || []).map((item) => ({ ...item }))
  error.value = ''
  await nextTick()
  if (dialog.value && !dialog.value.open) dialog.value.showModal()
})

async function save() {
  if (!draft.value) return
  saving.value = true
  error.value = ''
  try {
    await galleryApi.updateAsset(draft.value, tags.value, emotions.value)
    emit('saved')
    close()
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '保存失败'
  } finally {
    saving.value = false
  }
}

function close() {
  dialog.value?.close()
  emit('close')
}

async function removeAsset() {
  if (!draft.value) return
  saving.value = true
  error.value = ''
  try {
    await galleryApi.deleteAsset(draft.value.id)
    deleteOpen.value = false
    emit('deleted')
    close()
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '删除失败'
  } finally {
    saving.value = false
  }
}

async function rebuildThumbnail() {
  const asset = draft.value
  if (!asset || asset.file_valid === false) return
  saving.value = true
  error.value = ''
  try {
    await galleryApi.rebuildThumbnail(asset.id, 640)
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '缩略图重建失败'
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <dialog ref="dialog" class="drawer-dialog" aria-labelledby="asset-detail-title" @cancel.prevent="close" @close="emit('close')">
    <div v-if="draft" class="drawer">
      <header class="drawer__header">
        <div><span>资产详情</span><h2 id="asset-detail-title">{{ draft.title || `图片 #${draft.id}` }}</h2></div>
        <button type="button" class="icon-button" aria-label="关闭详情" @click="close">×</button>
      </header>
      <div class="drawer__preview"><img v-if="draft.file_valid !== false" :src="galleryApi.fileUrl(draft.id)" :alt="draft.caption || draft.title || ''" /><div v-else class="drawer__invalid">原图文件已失效，当前资产不能审核通过。</div></div>
      <form class="drawer__form" @submit.prevent="save">
        <label>标题<input v-model="draft.title" maxlength="160" /></label>
        <label>说明<textarea v-model="draft.caption" rows="3" maxlength="1000" /></label>
        <TagPicker v-model="tags" :tag-counts="tagCounts" :definitions="definitions" :aliases="aliases" label="图片标签" allow-create hide-intensity />
        <EmotionProfileEditor v-model="emotions" :tags="tags" :definitions="definitions" />
        <dl class="asset-facts">
          <div><dt>引用</dt><dd>{{ draft.asset_ref }}</dd></div>
          <div><dt>来源</dt><dd>{{ draft.source || '本地导入' }}</dd></div>
          <div><dt>类型</dt><dd>{{ draft.mime_type }}</dd></div>
          <div><dt>审核</dt><dd>{{ draft.tags.includes('needs-review') ? '待审核' : '已通过' }}</dd></div>
          <div><dt>安全</dt><dd>{{ draft.tags.includes('safety:restricted') ? '受限' : draft.tags.includes('safety:safe') ? '可用于聊天' : '未确认' }}</dd></div>
          <div><dt>SHA-256</dt><dd class="hash-value">{{ draft.sha256 }}</dd></div>
        </dl>
        <p v-if="error" class="form-error" role="alert">{{ error }}</p>
        <footer class="dialog-actions">
          <button type="button" class="button danger ghost-danger" :disabled="saving" @click="deleteOpen = true">删除资产</button>
          <button v-if="draft.file_valid !== false" type="button" class="button secondary" :disabled="saving" @click="rebuildThumbnail">重建缩略图</button>
          <button type="button" class="button ghost" @click="close">取消</button>
          <button type="submit" class="button primary" :disabled="saving">{{ saving ? '保存中…' : '保存修改' }}</button>
        </footer>
      </form>
    </div>
  </dialog>
  <ConfirmDialog
    :open="deleteOpen"
    title="删除这张本地资产？"
    description="原图、缩略图和检索索引将被移除，并保留 tombstone 防止旧引用被复用。"
    confirm-label="确认删除"
    danger
    :busy="saving"
    @close="deleteOpen = false"
    @confirm="removeAsset"
  />
</template>
