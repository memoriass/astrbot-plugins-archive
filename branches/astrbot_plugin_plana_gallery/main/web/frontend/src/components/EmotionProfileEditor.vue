<script setup lang="ts">
import { computed, watch } from 'vue'
import type { EmotionProfile, TagDefinition } from '../types'
import { tagDescription, tagLabel } from '../utils/tags'
import { emotionProfileWarnings, intensityGuide, intensityLevels } from '../utils/emotionGuides'

const props = withDefaults(defineProps<{
  modelValue: EmotionProfile[]
  tags: string[]
  definitions?: TagDefinition[]
  compact?: boolean
}>(), { definitions: () => [], compact: false })

const emit = defineEmits<{ 'update:modelValue': [value: EmotionProfile[]] }>()
const emotionTags = computed(() => props.tags.filter((tag) => tag.startsWith('emotion:')))
const warnings = computed(() => emotionProfileWarnings(props.modelValue))

function synchronized() {
  const current = new Map(props.modelValue.map((item) => [item.emotion_tag, item]))
  const next = emotionTags.value.map((emotionTag, index) => current.get(emotionTag) || {
    emotion_tag: emotionTag,
    intensity: 2 as const,
    prominence: index === 0 ? 'primary' as const : 'secondary' as const,
    source: 'manual',
  })
  if (next.length && !next.some((item) => item.prominence === 'primary')) next[0] = { ...next[0], prominence: 'primary' }
  if (JSON.stringify(next) !== JSON.stringify(props.modelValue)) emit('update:modelValue', next)
}

function setIntensity(tag: string, intensity: 1 | 2 | 3) {
  emit('update:modelValue', props.modelValue.map((item) => item.emotion_tag === tag ? { ...item, intensity, source: 'manual' } : item))
}

function setPrimary(tag: string) {
  emit('update:modelValue', props.modelValue.map((item) => ({ ...item, prominence: item.emotion_tag === tag ? 'primary' : 'secondary', source: 'manual' })))
}

watch([emotionTags, () => props.modelValue], synchronized, { immediate: true, deep: true })
</script>

<template>
  <section class="emotion-editor" :class="{ compact }" aria-label="情绪强度与主次">
    <header><div><strong>情绪强度</strong><span>每个情绪分别设置强度，并选择一个主情绪</span></div></header>
    <p v-if="!modelValue.length" class="empty-inline">选择一个或多个情绪标签后，可设置各自强度。</p>
    <article v-for="item in modelValue" :key="item.emotion_tag" class="emotion-editor__row">
      <button type="button" class="emotion-primary" :class="{ active: item.prominence === 'primary' }" :aria-pressed="item.prominence === 'primary'" :aria-label="`将 ${tagLabel(item.emotion_tag, definitions)} 设为主情绪`" @click="setPrimary(item.emotion_tag)">★</button>
      <div class="emotion-editor__copy"><strong>{{ tagLabel(item.emotion_tag, definitions) }}</strong><span>{{ tagDescription(item.emotion_tag, definitions) || item.emotion_tag }}</span><p class="intensity-current"><b>{{ intensityGuide(item.emotion_tag, item.intensity).label }}</b>{{ intensityGuide(item.emotion_tag, item.intensity).cue }} · 例如：{{ intensityGuide(item.emotion_tag, item.intensity).example }}</p><details v-if="!compact" class="intensity-guide"><summary>查看三档对照</summary><ol><li v-for="guide in intensityLevels" :key="guide.level" :class="{ active: item.intensity === guide.level }"><strong>{{ guide.label }}</strong><span>{{ intensityGuide(item.emotion_tag, guide.level).example }}</span></li></ol></details></div>
      <div class="intensity-control" role="group" :aria-label="`${tagLabel(item.emotion_tag, definitions)}强度`">
        <button v-for="level in ([1, 2, 3] as const)" :key="level" type="button" :class="{ active: item.intensity === level }" :aria-pressed="item.intensity === level" @click="setIntensity(item.emotion_tag, level)">{{ ['轻', '中', '强'][level - 1] }}</button>
      </div>
    </article>
    <div v-if="warnings.length" class="emotion-editor__warnings" role="status"><strong>需要确认</strong><p v-for="warning in warnings" :key="warning">{{ warning }}</p></div>
    <p v-if="modelValue.length" class="emotion-editor__summary">{{ modelValue.map((item) => `${tagLabel(item.emotion_tag, definitions)}·${['轻', '中', '强'][item.intensity - 1]}${item.prominence === 'primary' ? '（主）' : ''}`).join(' + ') }}</p>
  </section>
</template>
