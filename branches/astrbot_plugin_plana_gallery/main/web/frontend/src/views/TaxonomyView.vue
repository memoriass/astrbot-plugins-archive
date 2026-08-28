<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { galleryApi } from '../api'
import type { TagAlias, TagDefinition } from '../types'
import { tagCategoryLabels, tagDescription, tagLabel, tagSearchText } from '../utils/tags'
import { intensityLevels } from '../utils/emotionGuides'

const definitions = ref<TagDefinition[]>([])
const aliases = ref<TagAlias[]>([])
const freeTags = ref<string[]>([])
const loading = ref(true)
const error = ref('')
const tagCounts = ref<Record<string, number>>({})
const editing = ref<TagDefinition | null>(null)
const editAliases = ref('')
const saving = ref(false)
const editorDialog = ref<HTMLDialogElement | null>(null)
const search = ref('')
const hiddenDefinitionCategories = new Set(['role', 'intensity', 'safety'])
const definitionCategory = (item: TagDefinition) => item.tag.includes(':') ? item.tag.split(':', 1)[0] : (item.facet || 'custom')
const visibleDefinitions = computed(() => definitions.value.filter((item) => !hiddenDefinitionCategories.has(definitionCategory(item))))
const visibleDefinitionTags = computed(() => new Set(visibleDefinitions.value.map((item) => item.tag)))
const visibleAliases = computed(() => aliases.value.filter((item) => visibleDefinitionTags.value.has(item.canonical_tag)))
const incompleteDefinitions = computed(() => visibleDefinitions.value.filter((item) => !item.label.trim() || item.label === item.tag || !item.description.trim()).length)
const freeTagUsage = computed(() => freeTags.value.reduce((total, tag) => total + (tagCounts.value[tag] || 0), 0))
const groups = computed(() => {
  const result = new Map<string, TagDefinition[]>()
  const keyword = search.value.trim().toLowerCase()
  for (const definition of visibleDefinitions.value.filter((item) => !keyword || tagSearchText(item.tag, definitions.value, aliases.value).includes(keyword))) {
    const category = definitionCategory(definition)
    const rows = result.get(category) || []
    rows.push(definition)
    result.set(category, rows)
  }
  return [...result.entries()]
})
const filteredFreeTags = computed(() => {
  const keyword = search.value.trim().toLowerCase()
  return freeTags.value.filter((tag) => !keyword || tag.toLowerCase().includes(keyword))
})
const filteredAliases = computed(() => {
  const keyword = search.value.trim().toLowerCase()
  return visibleAliases.value.filter((item) => !keyword || item.alias.includes(keyword) || item.canonical_tag.includes(keyword))
})

async function load() {
  loading.value = true
  error.value = ''
  try {
    const [data, status] = await Promise.all([galleryApi.taxonomy(), galleryApi.status()])
    definitions.value = data.definitions || []
    aliases.value = data.aliases || []
    freeTags.value = data.orphaned_tags || []
    tagCounts.value = status.tag_counts || {}
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '加载失败'
  } finally {
    loading.value = false
  }
}

function categoryLabel(category: string) {
  return tagCategoryLabels[category] || '其他标签'
}

function editDefinition(row: TagDefinition) {
  editing.value = { ...row }
  editAliases.value = aliases.value.filter((item) => item.canonical_tag === row.tag).map((item) => item.alias).join(', ')
}

async function saveDefinition() {
  if (!editing.value) return
  saving.value = true
  error.value = ''
  try {
    await galleryApi.saveTagDefinition(
      editing.value.tag,
      editing.value.label,
      editing.value.description,
      editAliases.value.split(/[,，\n]/).map((item) => item.trim()).filter(Boolean),
    )
    editing.value = null
    await load()
  } catch (reason) {
    const message = reason instanceof Error ? reason.message : '保存失败'
    error.value = message === 'alias_conflict'
      ? '某个别名已属于其他标签定义，请先检查别名关系。'
      : message === 'alias_conflicts_with_canonical'
        ? '别名不能与另一个标签定义的稳定键相同。'
        : message
  } finally {
    saving.value = false
  }
}

onMounted(load)

watch(editing, async (value) => {
  await nextTick()
  if (value && editorDialog.value && !editorDialog.value.open) editorDialog.value.showModal()
  if (!value) editorDialog.value?.close()
})
</script>

<template>
  <div class="view-page">
    <header class="page-header"><div><h1>标签体系</h1><p>标签按图片实际含义直接归一；无法确定情绪或语境的素材会进入待审核，不在这里手工建立映射。</p></div><button type="button" class="button secondary" @click="load">刷新统计</button></header>
    <section class="taxonomy-summary">
      <article><strong>{{ visibleDefinitions.length }}</strong><span>标签定义</span></article><article><strong>{{ visibleAliases.length }}</strong><span>检索别名</span></article><article><strong>{{ freeTags.length }}</strong><span>内容与自由标签</span></article><article><strong>{{ incompleteDefinitions }}</strong><span>缺少名称或说明</span></article>
    </section>
    <div class="taxonomy-toolbar"><label for="taxonomy-search">查找标签</label><input id="taxonomy-search" v-model="search" type="search" placeholder="搜索稳定键、显示名称、说明或别名" /><span>自由标签关联 {{ freeTagUsage }} 次资产标注</span></div>
    <p v-if="error" class="page-error" role="alert">{{ error }}</p>
    <div v-if="loading" class="grid-state" role="status">正在整理标签体系…</div>
    <div v-else class="taxonomy-layout">
      <section class="taxonomy-main">
        <div v-if="!groups.length" class="grid-state"><strong>没有匹配的标签</strong><p>尝试搜索其他名称、说明或别名。</p></div>
        <article v-for="[category, rows] in groups" :key="category" class="taxonomy-card">
          <header><div><span>标签分类</span><h2>{{ categoryLabel(category) }}</h2></div><strong>{{ rows.length }} 项</strong></header>
          <div class="taxonomy-table" role="table" :aria-label="`${categoryLabel(category)}标签`">
            <div v-for="row in rows" :key="row.tag" class="taxonomy-row" role="row"><div role="cell"><strong>{{ tagLabel(row.tag, definitions) }}</strong><code>{{ row.tag }}</code></div><p role="cell">{{ tagDescription(row.tag, definitions) || '暂无说明' }}</p><span role="cell">{{ row.asset_count }} 张</span><button type="button" class="button ghost" @click="editDefinition(row)">编辑</button></div>
          </div>
        </article>
      </section>
      <aside class="taxonomy-side">
        <section class="side-card intensity-rubric"><h2>强度标注准则</h2><p>强度描述图片表达幅度，不代表 AI 判断置信度。具体情绪示例会显示在资产编辑器中。</p><article v-for="level in intensityLevels" :key="level.level"><header><strong>{{ level.label }}</strong><span>{{ level.cue }}</span></header><div><span>通用线索</span><code>{{ level.example }}</code></div></article></section>
        <section class="side-card"><h2>内容与自由标签</h2><p>这些标签按原义保留。需要补充情绪或语境的图片会直接出现在待审核队列。</p><div class="orphan-list"><article v-for="tag in filteredFreeTags" :key="tag"><div><span class="tag">{{ tag }} <small>{{ tagCounts[tag] || 0 }}</small></span></div></article><p v-if="!filteredFreeTags.length" class="empty-inline">没有匹配的自由标签。</p></div></section>
        <section class="side-card"><h2>别名关系</h2><p>搜索和导入时会把常见写法直接归一到右侧标签定义。</p><div class="alias-list"><div v-for="item in filteredAliases" :key="item.alias"><code>{{ item.alias }}</code><span>→</span><code>{{ item.canonical_tag }}</code></div><p v-if="!filteredAliases.length" class="empty-inline">没有匹配的别名关系。</p></div></section>
      </aside>
    </div>
    <dialog ref="editorDialog" class="modal-dialog" aria-labelledby="definition-title" @cancel.prevent="editing = null" @close="editing = null">
      <form v-if="editing" class="modal-card" @submit.prevent="saveDefinition">
        <header class="dialog-header"><div><span>标签定义</span><h2 id="definition-title">编辑 {{ editing.tag }}</h2></div><button type="button" class="icon-button" aria-label="关闭标签编辑" @click="editing = null">×</button></header>
        <label>显示名称<input v-model="editing.label" maxlength="120" /></label>
        <label>说明<textarea v-model="editing.description" rows="3" maxlength="500" /></label>
        <label>别名<input v-model="editAliases" placeholder="例如：高兴，开心，庆祝成功" /></label>
        <p class="hint">可使用中英文逗号或换行分隔。别名不能占用其他标签定义或已有别名；稳定键不会在这里修改。</p>
        <footer class="dialog-actions"><button type="button" class="button ghost" @click="editing = null">取消</button><button type="submit" class="button primary" :disabled="saving">保存定义</button></footer>
      </form>
    </dialog>
  </div>
</template>
