<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { galleryApi } from '../api'
import TagPicker from '../components/TagPicker.vue'
import EmotionProfileEditor from '../components/EmotionProfileEditor.vue'
import type { DiagnosticResult, EmotionProfile, TagAlias, TagDefinition } from '../types'

const query = ref('')
const facets = ref<string[]>([])
const tagCounts = ref<Record<string, number>>({})
const definitions = ref<TagDefinition[]>([])
const aliases = ref<TagAlias[]>([])
const emotions = ref<EmotionProfile[]>([])
const result = ref<DiagnosticResult | null>(null)
const loading = ref(false)
const error = ref('')
const feedback = ref<Record<string, string>>({})
const jobCounts = ref<Record<string, number>>({})

onMounted(async () => {
  const status = await galleryApi.status()
  tagCounts.value = status.tag_counts
  definitions.value = status.definitions || []
  aliases.value = status.aliases || []
  const jobs = await galleryApi.jobs().catch(() => null)
  jobCounts.value = jobs?.counts || {}
})

async function run() {
  if (!query.value.trim()) return
  loading.value = true
  error.value = ''
  try {
    result.value = await galleryApi.diagnosticsQuery(query.value, facets.value, emotions.value)
    feedback.value = {}
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '检索失败'
  } finally {
    loading.value = false
  }
}

async function sendFeedback(assetRef: string, action: 'useful' | 'negative' | 'skipped') {
  if (!result.value) return
  feedback.value = { ...feedback.value, [assetRef]: 'saving' }
  try {
    await galleryApi.diagnosticsFeedback(result.value.request_id, assetRef, action, query.value)
    feedback.value = { ...feedback.value, [assetRef]: action }
  } catch (reason) {
    feedback.value = { ...feedback.value, [assetRef]: reason instanceof Error ? reason.message : 'failed' }
  }
}

const reasonLabels: Record<string, string> = {
  explicit_exclusion: '显式排除',
  needs_review: '待审核',
  restricted: '安全受限',
  missing_safe_tag: '未确认安全状态',
  file_invalid: '本地文件失效',
}
</script>

<template>
  <div class="view-page">
    <header class="page-header"><div><h1>检索诊断</h1><p>输入聊天语境并点选预期标签，检查候选是否符合直觉。</p></div></header>
    <section class="diagnostic-form">
      <label for="diagnostic-query">聊天语境<textarea id="diagnostic-query" v-model="query" rows="4" placeholder="例如：用户说‘好耶，终于完成了’，Plana 回复‘值得庆祝一下’" /></label>
      <TagPicker v-model="facets" :tag-counts="tagCounts" :definitions="definitions" :aliases="aliases" label="预期标签（可选）" hide-intensity />
      <EmotionProfileEditor v-model="emotions" :tags="facets" :definitions="definitions" compact />
      <p v-if="error" class="form-error" role="alert">{{ error }}</p>
      <button type="button" class="button primary" :disabled="loading || !query.trim()" @click="run">{{ loading ? '正在检索…' : '运行诊断' }}</button>
    </section>
    <section class="diagnostic-results" aria-live="polite">
      <header><div><h2>候选结果</h2><p v-if="result">{{ result.selection_hint.mode === 'direct' ? `强规则会直接选择 ${result.selection_hint.asset_ref}` : '候选差距不足，将交给轻量模型或放弃出图' }}</p></div><span>{{ result?.candidates.length || 0 }} 个</span></header>
      <article v-for="(candidate, index) in result?.candidates || []" :key="candidate.asset_ref" class="candidate-row candidate-card">
        <strong>#{{ index + 1 }}</strong>
        <img :src="galleryApi.thumbnailUrl(candidate.asset_id, 320)" :alt="candidate.caption || ''" loading="lazy" />
        <div class="candidate-copy"><code>{{ candidate.asset_ref }}</code><p>{{ candidate.caption || '暂无说明' }}</p><div v-if="candidate.emotions?.length" class="candidate-emotions"><span v-for="item in candidate.emotions" :key="item.emotion_tag" :class="{ matched: candidate.matched_emotions?.includes(item.emotion_tag) }">{{ item.emotion_tag }} · {{ ['轻', '中', '强'][item.intensity - 1] }}{{ item.prominence === 'primary' ? '（主）' : '' }}</span></div><div class="tag-cloud"><span v-for="tag in candidate.tags" :key="tag" class="mini-tag" :class="{ matched: candidate.matched_facets.includes(tag) }">{{ tag }}</span></div></div>
        <div class="score-breakdown"><div class="score"><strong>{{ candidate.score }}</strong><span>综合分</span></div><dl><div v-for="(value, key) in candidate.score_breakdown" :key="key"><dt>{{ key }}</dt><dd>{{ value }}</dd></div></dl></div>
        <div class="candidate-feedback" role="group" :aria-label="`${candidate.asset_ref} 诊断反馈`"><button type="button" class="button ghost" @click="sendFeedback(candidate.asset_ref, 'useful')">有用</button><button type="button" class="button ghost" @click="sendFeedback(candidate.asset_ref, 'negative')">无用</button><button type="button" class="button ghost" @click="sendFeedback(candidate.asset_ref, 'skipped')">跳过</button><span v-if="feedback[candidate.asset_ref]">{{ feedback[candidate.asset_ref] }}</span></div>
      </article>
      <div v-if="!loading && !result?.candidates.length" class="grid-state"><strong>等待诊断</strong><p>输入一段聊天语境，查看 Gallery 会返回哪些本地图片。</p></div>
    </section>
    <div class="diagnostic-secondary">
      <section class="side-card exclusion-panel"><h2>排除原因</h2><p>生产候选只包含已审核、安全且文件有效的资产。</p><div v-if="result?.exclusions.length" class="exclusion-list"><div v-for="item in result.exclusions" :key="`${item.asset_ref}:${item.reason}`"><code>{{ item.asset_ref }}</code><span>{{ reasonLabels[item.reason] || item.reason }}</span></div></div><div v-else class="empty-inline">运行诊断后显示最近的排除样本。</div></section>
      <section class="side-card jobs-panel"><h2>后台任务</h2><p>缩略图与索引任务独立处理，失败不会阻塞原图管理。</p><div class="job-counts"><span v-for="(count, status) in jobCounts" :key="status"><strong>{{ count }}</strong>{{ status }}</span></div></section>
    </div>
  </div>
</template>
