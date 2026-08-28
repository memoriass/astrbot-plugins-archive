<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'
import { galleryApi } from '../api'
import type { TagAlias, TagDefinition } from '../types'
import TagPicker from './TagPicker.vue'

const props = withDefaults(defineProps<{
  open: boolean
  tagCounts: Record<string, number>
  definitions?: TagDefinition[]
  aliases?: TagAlias[]
}>(), { definitions: () => [], aliases: () => [] })
const emit = defineEmits<{ close: []; imported: [] }>()
const dialog = ref<HTMLDialogElement | null>(null)
const mode = ref<'files' | 'path'>('files')
const files = ref<File[]>([])
const path = ref('')
const title = ref('')
const caption = ref('')
const tags = ref<string[]>([])
const busy = ref(false)
const error = ref('')

watch(() => props.open, async (open) => {
  await nextTick()
  if (open && dialog.value && !dialog.value.open) dialog.value.showModal()
  if (!open) dialog.value?.close()
})

async function submit() {
  error.value = ''
  if (mode.value === 'files' && !files.value.length) {
    error.value = '请先选择图片或 ZIP 文件。'
    return
  }
  if (mode.value === 'path' && !path.value.trim()) {
    error.value = '请输入本地图片或目录路径。'
    return
  }
  busy.value = true
  try {
    if (mode.value === 'files') await galleryApi.upload(files.value, tags.value)
    else await galleryApi.importPath(path.value, title.value, caption.value, tags.value)
    emit('imported')
    close()
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '导入失败'
  } finally {
    busy.value = false
  }
}

function close() {
  dialog.value?.close()
  emit('close')
}
</script>

<template>
  <dialog ref="dialog" class="modal-dialog" aria-labelledby="import-title" @cancel.prevent="close" @close="emit('close')">
    <form class="modal-card wide" @submit.prevent="submit">
      <header class="dialog-header"><div><span>本地入库</span><h2 id="import-title">导入图片资产</h2></div><button type="button" class="icon-button" aria-label="关闭导入" @click="close">×</button></header>
      <div class="segmented large" aria-label="导入方式"><button type="button" :class="{ active: mode === 'files' }" @click="mode = 'files'">上传文件 / ZIP</button><button type="button" :class="{ active: mode === 'path' }" @click="mode = 'path'">本地路径 / 目录</button></div>
      <label v-if="mode === 'files'" class="drop-zone">选择图片或 ZIP<input type="file" multiple accept="image/*,.zip" @change="files = Array.from(($event.target as HTMLInputElement).files || [])" /><span>{{ files.length ? `已选择 ${files.length} 个文件` : '点击选择，文件会复制到 Gallery 数据目录' }}</span></label>
      <div v-else class="form-grid"><label>本地路径<input v-model="path" placeholder="C:\images\reaction" /></label><label>标题<input v-model="title" placeholder="单图导入时可选" /></label><label class="full">说明<textarea v-model="caption" rows="2" /></label></div>
      <TagPicker v-model="tags" :tag-counts="tagCounts" :definitions="definitions" :aliases="aliases" label="入库标签（可选）" allow-create />
      <p class="hint">不选择标签时图片进入待审核；已有标签不会被强制改名。</p>
      <p v-if="error" class="form-error" role="alert">{{ error }}</p>
      <footer class="dialog-actions"><button type="button" class="button ghost" @click="close">取消</button><button type="submit" class="button primary" :disabled="busy">{{ busy ? '导入中…' : '开始导入' }}</button></footer>
    </form>
  </dialog>
</template>
