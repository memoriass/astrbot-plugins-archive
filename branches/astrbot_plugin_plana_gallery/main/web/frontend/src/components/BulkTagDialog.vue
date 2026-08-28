<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'
import type { TagAlias, TagDefinition } from '../types'
import TagPicker from './TagPicker.vue'

const props = withDefaults(defineProps<{
  open: boolean
  count: number
  tagCounts: Record<string, number>
  definitions?: TagDefinition[]
  aliases?: TagAlias[]
  reviewMode?: boolean
}>(), { definitions: () => [], aliases: () => [], reviewMode: false })
const emit = defineEmits<{
  close: []
  apply: [payload: { addTags: string[]; removeTags: string[]; approve: boolean }]
}>()
const dialog = ref<HTMLDialogElement | null>(null)
const addTags = ref<string[]>([])
const removeTags = ref<string[]>([])

watch(() => props.open, async (open) => {
  await nextTick()
  if (open && dialog.value && !dialog.value.open) dialog.value.showModal()
  if (!open) dialog.value?.close()
})

function submit(approve: boolean) {
  emit('apply', { addTags: addTags.value, removeTags: removeTags.value, approve })
}

function close() {
  dialog.value?.close()
  emit('close')
}
</script>

<template>
  <dialog ref="dialog" class="modal-dialog" aria-labelledby="bulk-title" @cancel.prevent="close" @close="emit('close')">
    <div class="modal-card wide">
      <header class="dialog-header"><div><span>批量整理</span><h2 id="bulk-title">处理已选 {{ count }} 张图片</h2></div><button type="button" class="icon-button" aria-label="关闭批量整理" @click="close">×</button></header>
      <p class="callout">添加和移除标签不会自动改变审核状态。只有点击“保存并确认通过”才会让待审核图片进入候选。</p>
      <TagPicker v-model="addTags" :tag-counts="tagCounts" :definitions="definitions" :aliases="aliases" label="要添加的标签" allow-create />
      <TagPicker v-model="removeTags" :tag-counts="tagCounts" :definitions="definitions" :aliases="aliases" label="要移除的标签" compact />
      <footer class="dialog-actions">
        <button type="button" class="button ghost" @click="close">取消</button>
        <button type="button" class="button secondary" @click="submit(false)">仅保存标签</button>
        <button v-if="reviewMode" type="button" class="button primary" @click="submit(true)">保存并确认通过</button>
      </footer>
    </div>
  </dialog>
</template>
