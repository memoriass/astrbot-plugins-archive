import type { EmotionProfile } from '../types'

export interface IntensityGuide {
  level: 1 | 2 | 3
  label: string
  cue: string
  example: string
}

export const intensityLevels: IntensityGuide[] = [
  { level: 1, label: '轻', cue: '只作为语气点缀，不抢占文字内容', example: '有点、还好、轻微反应' },
  { level: 2, label: '中', cue: '表情含义清晰，适合普通闲聊反应', example: '明确开心、疑惑或无奈' },
  { level: 3, label: '强', cue: '动作或表情幅度明显，只用于强烈语境', example: '重复强调、强烈惊喜或明显崩溃' },
]

const emotionExamples: Record<string, [string, string, string]> = {
  'emotion:happy': ['浅笑、满意', '明显开心、愉快回应', '喜出望外、开心到跳起来'],
  'emotion:excited': ['有点期待', '兴奋庆祝、精神振奋', '激动欢呼、好耶到停不下来'],
  'emotion:amused': ['轻轻被逗笑', '明显觉得好笑', '笑到绷不住或拍桌'],
  'emotion:affection': ['温柔好感', '明显喜欢、贴贴', '强烈宠溺或狠狠爱了'],
  'emotion:grateful': ['礼貌感谢', '真诚感激、感到暖心', '非常感动或郑重感谢'],
  'emotion:proud': ['小小满意', '得意、自豪', '扬眉吐气或成就感爆棚'],
  'emotion:relieved': ['稍微放心', '明显松了一口气', '终于解脱、压力瞬间释放'],
  'emotion:hopeful': ['有一点期待', '明确期待好结果', '满怀希望、迫不及待'],
  'emotion:playful': ['轻微卖萌', '明显俏皮或坏笑', '活泼捉弄、玩心完全主导'],
  'emotion:calm': ['稍显放松', '明显平静安稳', '非常从容、完全不受干扰'],
  'emotion:surprised': ['略感意外', '明显惊讶', '震惊、目瞪口呆'],
  'emotion:confused': ['有一点没懂', '明显困惑、需要确认', '完全迷茫、满头问号'],
  'emotion:curious': ['稍微想看看', '明显好奇、关注后续', '强烈求知、迫切想弄明白'],
  'emotion:speechless': ['轻微无奈', '明显无语、啊这', '离谱到麻了或不知道说什么'],
  'emotion:helpless': ['轻轻叹气', '明显无奈、只能接受', '完全没办法、心累到放弃抵抗'],
  'emotion:shy': ['略微不好意思', '明显害羞、脸红', '害羞到躲开或不敢回应'],
  'emotion:embarrassed': ['轻微尴尬', '明显社死或出糗', '尴尬到想逃离现场'],
  'emotion:sad': ['有点失落', '明显难过、委屈', '非常伤心或控制不住想哭'],
  'emotion:wronged': ['稍感不公平', '明显委屈、含泪控诉', '委屈到崩溃或强烈求安慰'],
  'emotion:disappointed': ['稍感遗憾', '明显失望', '期待彻底落空、非常沮丧'],
  'emotion:frustrated': ['略感受阻', '明显挫败、做不下去', '反复失败到接近崩溃'],
  'emotion:guilty': ['略有歉意', '明显内疚、知道做错了', '强烈自责、迫切希望补救'],
  'emotion:angry': ['轻微不满', '明显生气、反对', '火大、气炸或强烈愤怒'],
  'emotion:annoyed': ['略感烦扰', '明显烦躁、不耐烦', '被持续打扰到接近爆发'],
  'emotion:afraid': ['有点担心害怕', '明显受惊或恐惧', '非常惊恐、想立即躲避'],
  'emotion:nervous': ['轻微忐忑', '明显紧张、焦虑', '高度紧绷、坐立不安'],
  'emotion:panicked': ['稍显慌乱', '明显手忙脚乱', '突发惊慌、完全失去从容'],
  'emotion:disgusted': ['轻微嫌弃', '明显反感', '强烈恶心或排斥'],
  'emotion:tired': ['有一点累', '明显疲惫、没精神', '累瘫、完全不想动'],
  'emotion:bored': ['略感无聊', '明显提不起兴趣', '无聊到抓狂或急需换话题'],
  'emotion:comfort': ['温和陪伴', '明确安慰和支持', '强烈关怀；严肃语境仍应阻止自动附图'],
}

const positive = new Set(['emotion:happy', 'emotion:excited', 'emotion:amused', 'emotion:affection', 'emotion:grateful', 'emotion:proud', 'emotion:relieved', 'emotion:hopeful', 'emotion:playful', 'emotion:calm'])
const negative = new Set(['emotion:sad', 'emotion:wronged', 'emotion:disappointed', 'emotion:frustrated', 'emotion:guilty', 'emotion:angry', 'emotion:annoyed', 'emotion:afraid', 'emotion:nervous', 'emotion:panicked', 'emotion:disgusted'])

export function intensityGuide(emotionTag: string, level: 1 | 2 | 3): IntensityGuide {
  const base = intensityLevels[level - 1]
  return { ...base, example: emotionExamples[emotionTag]?.[level - 1] || base.example }
}

export function emotionProfileWarnings(profiles: EmotionProfile[]) {
  const warnings: string[] = []
  const strong = profiles.filter((item) => item.intensity === 3)
  if (strong.length > 1) warnings.push('当前包含多个强烈情绪，请确认图片确实同时表达这些情绪。')
  if (strong.some((item) => positive.has(item.emotion_tag)) && strong.some((item) => negative.has(item.emotion_tag))) {
    warnings.push('检测到强烈正向与负向情绪并存；可以保留，但建议核对主情绪和图片语境。')
  }
  if (profiles.length > 1 && !profiles.some((item) => item.prominence === 'primary')) warnings.push('复合情绪必须指定一个主情绪。')
  return warnings
}
