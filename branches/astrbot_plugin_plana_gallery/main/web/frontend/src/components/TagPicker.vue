<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { TagAlias, TagDefinition } from '../types'
import {
  groupTags,
  normalizeTagInput,
  reservedTagPrefixes,
  suggestTags,
  tagDescription,
  tagLabel,
  tagSearchText,
} from '../utils/tags'

const props = withDefaults(defineProps<{
  modelValue: string[]
  tagCounts: Record<string, number>
  definitions?: TagDefinition[]
  aliases?: TagAlias[]
  label?: string
  allowCreate?: boolean
  compact?: boolean
  hideIntensity?: boolean
}>(), {
  definitions: () => [],
  aliases: () => [],
  label: '选择标签',
  allowCreate: false,
  compact: false,
  hideIntensity: false,
})

const emit = defineEmits<{ 'update:modelValue': [value: string[]] }>()
const search = ref('')
const customTag = ref('')
const createConfirmed = ref(false)
const groups = computed(() => {
  const keyword = search.value.trim().toLowerCase()
  return groupTags(props.tagCounts, props.definitions)
    .map((group) => ({
      ...group,
      options: group.options.filter((option) => !keyword || tagSearchText(option.tag, props.definitions, props.aliases).includes(keyword)),
    }))
    .filter((group) => group.options.length)
})
const visibleModelValue = computed(() => props.modelValue.filter((tag) => {
  if (tag === 'needs-review') return false
  const prefix = tag.includes(':') ? tag.split(':', 1)[0] : 'free'
  return !['role', 'intensity', 'safety'].includes(prefix)
}))
const normalizedCustomTag = computed(() => normalizeTagInput(customTag.value))
const customSuggestions = computed(() => suggestTags(
  customTag.value,
  props.tagCounts,
  props.definitions,
  props.aliases,
))
const exactSuggestion = computed(() => customSuggestions.value.find((item) => item.score === 100))
const customPrefix = computed(() => normalizedCustomTag.value.includes(':') ? normalizedCustomTag.value.split(':', 1)[0] : '')
const customError = computed(() => {
  if (!normalizedCustomTag.value) return ''
  if (customPrefix.value && reservedTagPrefixes.has(customPrefix.value)) {
    return '系统标签不能在这里新建，请在“标签体系”中维护已有标签。'
  }
  return ''
})

function toggle(tag: string) {
  const next = props.modelValue.includes(tag)
    ? props.modelValue.filter((item) => item !== tag)
    : [...props.modelValue, tag]
  emit('update:modelValue', next)
}

function chooseSuggestion(tag: string) {
  if (!props.modelValue.includes(tag)) emit('update:modelValue', [...props.modelValue, tag])
  customTag.value = ''
}

function addCustom() {
  const tag = normalizedCustomTag.value
  if (!tag || customError.value) return
  if (exactSuggestion.value) {
    chooseSuggestion(exactSuggestion.value.tag)
    return
  }
  if (!createConfirmed.value) {
    createConfirmed.value = true
    return
  }
  if (!props.modelValue.includes(tag)) emit('update:modelValue', [...props.modelValue, tag])
  customTag.value = ''
}

watch(customTag, () => {
  createConfirmed.value = false
})
</script>

<template>
  <section class="tag-picker" :class="{ compact }" :aria-label="label">
    <div class="tag-picker__head">
      <div>
        <strong>{{ label }}</strong>
        <span>{{ visibleModelValue.length ? `已选 ${visibleModelValue.length} 个` : '从现有标签中选择，可按名称、说明或别名搜索' }}</span>
      </div>
      <input v-model="search" type="search" aria-label="搜索标签" placeholder="搜索名称、说明或别名" />
    </div>
    <div v-if="visibleModelValue.length" class="selected-tags" aria-label="已选标签">
      <button v-for="tag in visibleModelValue" :key="tag" type="button" class="tag selected" @click="toggle(tag)">
        {{ tagLabel(tag, definitions) }}
        <small v-if="tagLabel(tag, definitions) !== tag">{{ tag }}</small>
        <span aria-hidden="true">×</span>
      </button>
    </div>
    <div class="tag-groups">
      <div v-for="group in groups" :key="group.key" class="tag-group">
        <div class="tag-group__label">{{ group.label }}</div>
        <div class="tag-options">
          <button
            v-for="option in group.options"
            :key="option.tag"
            type="button"
            class="tag"
            :class="{ selected: modelValue.includes(option.tag) }"
            :aria-pressed="modelValue.includes(option.tag)"
            :title="tagDescription(option.tag, definitions) || option.tag"
            @click="toggle(option.tag)"
          >
            {{ tagLabel(option.tag, definitions) }} <small>{{ option.count }}</small>
          </button>
        </div>
      </div>
      <p v-if="!groups.length" class="empty-inline">没有匹配的现有标签。可换一个名称或别名搜索。</p>
    </div>
    <form v-if="allowCreate" class="custom-tag" @submit.prevent="addCustom">
      <label for="custom-tag-input">创建自由标签</label>
      <input id="custom-tag-input" v-model="customTag" placeholder="先输入名称检查重复项" autocomplete="off" />
      <button type="submit" class="button secondary" :disabled="!normalizedCustomTag || Boolean(customError)">
        {{ exactSuggestion ? '选择已有标签' : createConfirmed ? '确认创建自由标签' : '检查名称' }}
      </button>
      <p v-if="customError" class="form-error custom-tag__message" role="alert">{{ customError }}</p>
      <div v-else-if="customTag && customSuggestions.length" class="tag-suggestions" aria-live="polite">
        <strong>{{ exactSuggestion ? '已存在同名或同义标签' : '可能相近的现有标签' }}</strong>
        <button v-for="item in customSuggestions" :key="item.tag" type="button" @click="chooseSuggestion(item.tag)">
          <span>{{ item.label }} <small>{{ item.tag }}</small></span><em>{{ item.reason }} · {{ item.count }} 张</em>
        </button>
      </div>
      <p v-else-if="createConfirmed" class="custom-tag__message" role="status">
        将创建自由标签 <code>{{ normalizedCustomTag }}</code>。它只作为普通图片标签保留，之后可在“标签体系”中整理。
      </p>
    </form>
  </section>
</template>
