<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{ page: number; pageCount: number; total: number; pageSize: number }>()
const emit = defineEmits<{ page: [value: number]; 'page-size': [value: number] }>()
const pages = computed(() => {
  const start = Math.max(1, Math.min(props.page - 2, props.pageCount - 4))
  const end = Math.min(props.pageCount, start + 4)
  return Array.from({ length: Math.max(0, end - start + 1) }, (_, index) => start + index)
})
</script>

<template>
  <nav class="pagination" aria-label="图库分页">
    <span class="pagination__summary">共 {{ total }} 张</span>
    <button type="button" class="page-button" :disabled="page <= 1" aria-label="上一页" @click="emit('page', page - 1)">‹</button>
    <button v-if="pages[0] && pages[0] > 1" type="button" class="page-button" @click="emit('page', 1)">1</button>
    <span v-if="pages[0] && pages[0] > 2" aria-hidden="true">…</span>
    <button v-for="item in pages" :key="item" type="button" class="page-button" :class="{ active: item === page }" :aria-current="item === page ? 'page' : undefined" @click="emit('page', item)">{{ item }}</button>
    <span v-if="pages.at(-1) && pages.at(-1)! < pageCount - 1" aria-hidden="true">…</span>
    <button v-if="pages.at(-1) && pages.at(-1)! < pageCount" type="button" class="page-button" @click="emit('page', pageCount)">{{ pageCount }}</button>
    <button type="button" class="page-button" :disabled="page >= pageCount" aria-label="下一页" @click="emit('page', page + 1)">›</button>
    <label class="page-size">每页
      <select :value="pageSize" @change="emit('page-size', Number(($event.target as HTMLSelectElement).value))">
        <option :value="24">24</option><option :value="48">48</option><option :value="72">72</option><option :value="96">96</option>
      </select>
    </label>
  </nav>
</template>
