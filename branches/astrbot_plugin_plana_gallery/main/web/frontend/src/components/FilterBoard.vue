<script setup lang="ts">
import { computed, ref } from 'vue'
import type { AssetFilters } from '../types'
import { groupTags, tagLabel } from '../utils/tags'

const props = defineProps<{
  filters: AssetFilters
  tagCounts: Record<string, number>
  sources: Array<{ source: string; count: number }>
}>()
const emit = defineEmits<{ apply: []; reset: [] }>()
const expanded = ref(true)
const tagSearch = ref('')
const groups = computed(() => {
  const keyword = tagSearch.value.trim().toLowerCase()
  return groupTags(props.tagCounts)
    .map((group) => ({ ...group, options: group.options.filter((item) => !keyword || item.tag.includes(keyword)) }))
    .filter((group) => group.options.length)
})

function toggleTag(tag: string) {
  props.filters.tags = props.filters.tags.includes(tag)
    ? props.filters.tags.filter((item) => item !== tag)
    : [...props.filters.tags, tag]
}
</script>

<template>
  <section class="filter-board" aria-labelledby="filter-title">
    <header class="filter-board__header">
      <div>
        <h2 id="filter-title">组合筛选</h2>
        <p>像资料库一样按属性逐层缩小范围，无需记忆标签名称。</p>
      </div>
      <button type="button" class="button ghost" :aria-expanded="expanded" aria-controls="filter-content" @click="expanded = !expanded">
        {{ expanded ? '收起筛选' : '展开筛选' }}
      </button>
    </header>
    <div v-show="expanded" id="filter-content" class="filter-board__content">
      <div class="filter-row">
        <span class="filter-row__label">审核状态</span>
        <div class="tag-options">
          <button v-for="item in [{ value: 'all', label: '全部' }, { value: 'ready', label: '可使用' }, { value: 'pending', label: '待审核' }]" :key="item.value" type="button" class="tag" :class="{ selected: filters.review === item.value }" @click="filters.review = item.value as AssetFilters['review']">
            {{ item.label }}
          </button>
        </div>
      </div>
      <div v-if="sources.length" class="filter-row">
        <span class="filter-row__label">来源</span>
        <div class="tag-options">
          <button type="button" class="tag" :class="{ selected: !filters.source }" @click="filters.source = ''">全部来源</button>
          <button v-for="item in sources" :key="item.source" type="button" class="tag" :class="{ selected: filters.source === item.source }" @click="filters.source = item.source">
            {{ item.source }} <small>{{ item.count }}</small>
          </button>
        </div>
      </div>
      <div class="filter-row filter-row--search">
        <label class="filter-row__label" for="filter-tag-search">标签</label>
        <input id="filter-tag-search" v-model="tagSearch" type="search" placeholder="筛选下面的标签选项" />
        <div class="segmented" aria-label="标签匹配方式">
          <button type="button" :class="{ active: filters.tagMode === 'all' }" @click="filters.tagMode = 'all'">同时满足</button>
          <button type="button" :class="{ active: filters.tagMode === 'any' }" @click="filters.tagMode = 'any'">满足任一</button>
        </div>
      </div>
      <div v-for="group in groups" :key="group.key" class="filter-row">
        <span class="filter-row__label">{{ group.label }}</span>
        <div class="tag-options">
          <button v-for="option in group.options" :key="option.tag" type="button" class="tag" :class="{ selected: filters.tags.includes(option.tag) }" :aria-pressed="filters.tags.includes(option.tag)" @click="toggleTag(option.tag)">
            {{ tagLabel(option.tag) }} <small>{{ option.count }}</small>
          </button>
        </div>
      </div>
      <footer class="filter-actions">
        <span>{{ filters.tags.length ? `已选择 ${filters.tags.length} 个标签条件` : '尚未选择标签条件' }}</span>
        <button type="button" class="button ghost" @click="emit('reset')">清空条件</button>
        <button type="button" class="button primary" @click="emit('apply')">应用筛选</button>
      </footer>
    </div>
  </section>
</template>
