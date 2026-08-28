import type { TagAlias, TagDefinition } from '../types'

export interface TagOption {
  tag: string
  count: number
}

export interface TagGroup {
  key: string
  label: string
  options: TagOption[]
}

export interface TagSuggestion extends TagOption {
  label: string
  description: string
  score: number
  reason: string
}

export const tagCategoryLabels: Record<string, string> = {
  emotion: '情绪',
  tone: '语气',
  scene: '场景',
  free: '原有 / 自由标签',
}

export const hiddenTagPrefixes = new Set(['role', 'intensity', 'safety'])
export const reservedTagPrefixes = new Set(['emotion', 'tone', 'scene', 'role', 'intensity', 'safety'])

const legacyDisplay: Record<string, { label: string; description: string }> = {
  angry: { label: '生气', description: '生气、不满或强烈反驳' },
  baka: { label: '笨蛋', description: '轻度吐槽、调侃或嫌弃' },
  color: { label: '彩色', description: '彩色版本或视觉分类标签' },
  confused: { label: '疑惑', description: '困惑、不理解或需要确认' },
  cpu: { label: 'CPU', description: 'CPU、硬件或过载相关表情' },
  fool: { label: '犯傻', description: '犯傻、搞怪或自嘲' },
  givemoney: { label: '给钱', description: '付款、打赏或索要经费' },
  happy: { label: '开心', description: '开心、庆祝或积极回应' },
  like: { label: '赞同', description: '认可、点赞或表示支持' },
  meow: { label: '喵', description: '卖萌、猫系或轻松回应' },
  morning: { label: '早安', description: '早晨问候或起床场景' },
  reply: { label: '回复', description: '催促回应或强调回复动作' },
  sad: { label: '难过', description: '失落、委屈或悲伤' },
  see: { label: '围观', description: '观察、围观或等待后续' },
  shy: { label: '害羞', description: '害羞、被夸或轻微尴尬' },
  sigh: { label: '叹气', description: '无奈、疲惫或轻度吐槽' },
  sleep: { label: '睡觉', description: '困倦、休息或晚安' },
  surprised: { label: '惊讶', description: '意外、震惊或突然发现' },
  work: { label: '工作', description: '工作、加班或任务状态' },
  'emotion:happy': { label: '开心', description: '愉快、满足或一般积极回应' },
  'emotion:excited': { label: '兴奋', description: '期待实现、强烈开心或激动庆祝' },
  'emotion:amused': { label: '觉得好笑', description: '被逗笑、看乐子或轻松搞怪' },
  'emotion:affection': { label: '喜欢', description: '喜爱、亲近、宠溺或温柔回应' },
  'emotion:grateful': { label: '感谢', description: '感谢、被帮助或感到暖心' },
  'emotion:proud': { label: '得意', description: '自豪、得意或完成目标后的满足' },
  'emotion:relieved': { label: '松口气', description: '风险解除、终于完成或压力下降' },
  'emotion:hopeful': { label: '期待', description: '对接下来结果抱有希望、期待或积极预期' },
  'emotion:playful': { label: '俏皮', description: '卖萌、坏笑、轻度捉弄或活泼互动' },
  'emotion:calm': { label: '平静', description: '放松、安稳或低唤醒度的中性积极状态' },
  'emotion:surprised': { label: '惊讶', description: '意外、震惊或突然发现' },
  'emotion:confused': { label: '困惑', description: '不理解、迷茫或需要进一步确认' },
  'emotion:curious': { label: '好奇', description: '想了解后续、观察新鲜事物或主动探究' },
  'emotion:speechless': { label: '无语', description: '离谱、无奈或不知道如何回应' },
  'emotion:helpless': { label: '无奈', description: '知道状况却难以改变、叹气或被迫接受' },
  'emotion:shy': { label: '害羞', description: '被夸、亲密互动或轻微不好意思' },
  'emotion:embarrassed': { label: '尴尬', description: '社交尴尬、出糗或想回避现场' },
  'emotion:sad': { label: '难过', description: '悲伤、失落或受到打击' },
  'emotion:wronged': { label: '委屈', description: '受到误解、被欺负或含泪表达不公平' },
  'emotion:disappointed': { label: '失望', description: '期待落空、遗憾或结果不理想' },
  'emotion:frustrated': { label: '挫败', description: '努力受阻、反复失败或无从下手' },
  'emotion:guilty': { label: '内疚', description: '意识到过失、做错事或希望得到原谅' },
  'emotion:angry': { label: '生气', description: '愤怒、强烈不满或明确反对' },
  'emotion:annoyed': { label: '烦躁', description: '轻度生气、被打扰或不耐烦' },
  'emotion:afraid': { label: '害怕', description: '恐惧、受惊或感到威胁' },
  'emotion:nervous': { label: '紧张', description: '担心结果、焦虑或坐立不安' },
  'emotion:panicked': { label: '慌张', description: '突发状况下明显失措、急迫或惊慌' },
  'emotion:disgusted': { label: '嫌弃', description: '反感、恶心或强烈排斥' },
  'emotion:tired': { label: '疲惫', description: '累、没精神或需要休息' },
  'emotion:bored': { label: '无聊', description: '缺少兴趣、等待过久或想找点事情' },
  'emotion:comfort': { label: '关怀', description: '用于安慰、陪伴和表达关心的回应倾向' },
}

export function normalizeTagInput(value: string) {
  return value.trim().toLowerCase().replace(/\s+/g, '-').slice(0, 80)
}

export function groupTags(
  tagCounts: Record<string, number>,
  definitions: TagDefinition[] = [],
): TagGroup[] {
  const groups = new Map<string, TagOption[]>()
  const tags = new Set([...Object.keys(tagCounts), ...definitions.map((item) => item.tag)])
  for (const tag of tags) {
    if (tag === 'needs-review') continue
    const prefix = tag.includes(':') ? tag.split(':', 1)[0] : 'free'
    if (hiddenTagPrefixes.has(prefix)) continue
    const options = groups.get(prefix) || []
    options.push({ tag, count: tagCounts[tag] || 0 })
    groups.set(prefix, options)
  }
  const ordered = ['emotion', 'tone', 'scene', 'free']
  return [...ordered, ...[...groups.keys()].filter((key) => !ordered.includes(key)).sort()]
    .filter((key) => groups.has(key))
    .map((key) => ({
      key,
      label: tagCategoryLabels[key] || key,
      options: (groups.get(key) || []).sort((a, b) => b.count - a.count || a.tag.localeCompare(b.tag)),
    }))
}

export function tagDefinition(tag: string, definitions: TagDefinition[] = []) {
  return definitions.find((item) => item.tag === tag)
}

export function tagLabel(tag: string, definitions: TagDefinition[] = []) {
  const definition = tagDefinition(tag, definitions)
  if (definition?.label && definition.label !== tag) return definition.label
  if (legacyDisplay[tag]) return legacyDisplay[tag].label
  const separator = tag.indexOf(':')
  return separator >= 0 ? tag.slice(separator + 1) : tag
}

export function tagDescription(tag: string, definitions: TagDefinition[] = []) {
  return tagDefinition(tag, definitions)?.description || legacyDisplay[tag]?.description || ''
}

export function tagAliases(tag: string, aliases: TagAlias[] = []) {
  return aliases.filter((item) => item.canonical_tag === tag).map((item) => item.alias)
}

export function tagSearchText(tag: string, definitions: TagDefinition[] = [], aliases: TagAlias[] = []) {
  return [tag, tagLabel(tag, definitions), tagDescription(tag, definitions), ...tagAliases(tag, aliases)]
    .join(' ')
    .toLowerCase()
}

export function suggestTags(
  value: string,
  tagCounts: Record<string, number>,
  definitions: TagDefinition[] = [],
  aliases: TagAlias[] = [],
  limit = 5,
): TagSuggestion[] {
  const query = normalizeTagInput(value)
  if (!query) return []
  return groupTags(tagCounts, definitions)
    .flatMap((group) => group.options)
    .map((option) => {
      const label = tagLabel(option.tag, definitions)
      const description = tagDescription(option.tag, definitions)
      const terms = [option.tag, label, ...tagAliases(option.tag, aliases)].map(normalizeTagInput)
      let score = 0
      let reason = ''
      if (terms.includes(query)) {
        score = 100
        reason = '名称或别名完全一致'
      } else if (terms.some((term) => term.startsWith(query) || query.startsWith(term))) {
        score = 80
        reason = '名称前缀相近'
      } else if (terms.some((term) => term.includes(query) || query.includes(term))) {
        score = 60
        reason = '名称包含相同片段'
      }
      return { ...option, label, description, score, reason }
    })
    .filter((item) => item.score > 0)
    .sort((a, b) => b.score - a.score || b.count - a.count || a.tag.localeCompare(b.tag))
    .slice(0, limit)
}
