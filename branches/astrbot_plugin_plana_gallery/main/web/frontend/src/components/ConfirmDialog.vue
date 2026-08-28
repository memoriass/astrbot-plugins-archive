<script setup lang="ts">
import { nextTick, ref, useId, watch } from 'vue'

const props = withDefaults(defineProps<{
  open: boolean
  title: string
  description: string
  confirmLabel?: string
  danger?: boolean
  busy?: boolean
}>(), {
  confirmLabel: '确认',
  danger: false,
  busy: false,
})
const emit = defineEmits<{ close: []; confirm: [] }>()
const dialog = ref<HTMLDialogElement | null>(null)
const confirmButton = ref<HTMLButtonElement | null>(null)
const titleId = useId()
const descriptionId = useId()

watch(() => props.open, async (open) => {
  await nextTick()
  if (open && dialog.value && !dialog.value.open) {
    dialog.value.showModal()
    confirmButton.value?.focus()
  }
  if (!open) dialog.value?.close()
})

function close() {
  dialog.value?.close()
  emit('close')
}
</script>

<template>
  <dialog ref="dialog" class="modal-dialog" :aria-labelledby="titleId" :aria-describedby="descriptionId" @cancel.prevent="close" @close="emit('close')">
    <div class="modal-card confirm-card">
      <header class="dialog-header">
        <div><span>请确认</span><h2 :id="titleId">{{ title }}</h2></div>
        <button type="button" class="icon-button" aria-label="关闭确认窗口" @click="close">×</button>
      </header>
      <p :id="descriptionId" class="confirm-description">{{ description }}</p>
      <slot />
      <footer class="dialog-actions">
        <button type="button" class="button ghost" :disabled="busy" @click="close">取消</button>
        <button ref="confirmButton" type="button" class="button" :class="danger ? 'danger' : 'primary'" :disabled="busy" @click="emit('confirm')">
          {{ busy ? '处理中…' : confirmLabel }}
        </button>
      </footer>
    </div>
  </dialog>
</template>
