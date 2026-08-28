export interface GalleryAsset {
  id: number
  asset_ref: string
  sha256: string
  file_path: string
  original_path: string
  mime_type: string
  title: string
  caption: string
  tags: string[]
  emotions: EmotionProfile[]
  source: string
  created_at: number
  updated_at: number
  file_valid?: boolean
}

export interface EmotionProfile {
  emotion_tag: string
  intensity: 1 | 2 | 3
  prominence: 'primary' | 'secondary'
  source?: string
  suggestion_confidence?: number | null
}

export interface TagDefinition {
  tag: string
  facet: string
  label: string
  description: string
  managed: number
  asset_count: number
}

export interface TagAlias {
  alias: string
  canonical_tag: string
}

export interface DiagnosticCandidate {
  asset_id: number
  asset_ref: string
  caption: string
  tags: string[]
  emotions: EmotionProfile[]
  matched_facets: string[]
  matched_emotions?: string[]
  score: number
  score_breakdown: Record<string, number>
}

export interface DiagnosticExclusion {
  asset_ref: string
  reason: string
}

export interface DiagnosticResult {
  request_id: string
  candidates: DiagnosticCandidate[]
  exclusions: DiagnosticExclusion[]
  selection_hint: { mode: 'direct' | 'model_or_none'; asset_ref: string; score: number; margin: number }
}

export interface GalleryJob {
  id: number
  job_type: string
  status: string
  attempts: number
  error: string
  created_at: number
  available_at?: number
  updated_at?: number
}

export interface GalleryStatus {
  assets: number
  review_assets: number
  tags: number
  tag_counts: Record<string, number>
  tag_list: string[]
  fts_available: boolean
  definitions: TagDefinition[]
  aliases?: TagAlias[]
  orphaned_tags?: string[]
  governance?: {
    audited_assets: number
    audit_events: number
    last_batch: Record<string, unknown> | null
  }
}

export interface AssetPage {
  assets: GalleryAsset[]
  total: number
  page: number
  page_size: number
  page_count: number
  sources: Array<{ source: string; count: number }>
}

export interface AssetFilters {
  query: string
  tags: string[]
  excludeTags: string[]
  tagMode: 'all' | 'any'
  review: 'all' | 'ready' | 'pending'
  source: string
  sort: string
  page: number
  pageSize: number
}
