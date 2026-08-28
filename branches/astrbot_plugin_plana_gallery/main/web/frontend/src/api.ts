import type {
  AssetFilters,
  AssetPage,
  DiagnosticResult,
  GalleryAsset,
  GalleryJob,
  GalleryStatus,
  EmotionProfile,
} from './types'

const metaBase = document.querySelector<HTMLMetaElement>('meta[name="plana-gallery-api-base"]')
const defaultBase = '/api/plug/plana_gallery'

class GalleryApi {
  base = (metaBase?.content || defaultBase).replace(/\/$/, '')
  token = ''

  async request<T>(path: string, options: RequestInit & { json?: unknown } = {}): Promise<T> {
    const headers = new Headers(options.headers)
    if (this.token) headers.set('X-Plana-Gallery-Token', this.token)
    let body = options.body
    if (options.json !== undefined) {
      headers.set('Content-Type', 'application/json')
      body = JSON.stringify(options.json)
    }
    const response = await fetch(`${this.base}${path}`, { ...options, headers, body })
    const payload = await response.json().catch(() => ({ ok: false, error: 'invalid_response' }))
    if (!response.ok || payload.ok === false) {
      throw new Error(payload.error || `http_${response.status}`)
    }
    return payload as T
  }

  status() {
    return this.request<GalleryStatus & { ok: true }>('/api/status')
  }

  assets(filters: AssetFilters) {
    const params = new URLSearchParams({
      q: filters.query,
      tags: filters.tags.join(','),
      exclude_tags: filters.excludeTags.join(','),
      tag_mode: filters.tagMode,
      review: filters.review,
      source: filters.source,
      sort: filters.sort,
      page: String(filters.page),
      page_size: String(filters.pageSize),
    })
    return this.request<AssetPage & { ok: true }>(`/api/assets?${params}`)
  }

  updateAsset(asset: GalleryAsset, tags: string[], emotions: EmotionProfile[]) {
    return this.request<{ ok: true; asset: GalleryAsset }>('/api/assets/update', {
      method: 'POST',
      json: {
        id: asset.id,
        title: asset.title,
        caption: asset.caption,
        tags,
        emotions,
        expected_updated_at: asset.updated_at,
      },
    })
  }

  reviewCommit(
    assets: GalleryAsset[],
    acceptedSuggestions: Record<number, string[]>,
    addTags: string[],
    removeTags: string[],
    emotionProfiles: EmotionProfile[],
    approve: boolean,
  ) {
    return this.request<{ ok: true; count: number; updated: GalleryAsset[] }>('/api/review/commit', {
      method: 'POST',
      json: {
        changes: assets.map((asset) => ({
          id: asset.id,
          expected_updated_at: asset.updated_at,
          add_tags: acceptedSuggestions[asset.id] || [],
        })),
        add_tags: addTags,
        remove_tags: removeTags,
        emotion_profiles: emotionProfiles,
        approve,
      },
    })
  }

  batchTags(ids: number[], addTags: string[], removeTags: string[], approve = false) {
    return this.request<{ ok: boolean; count: number }>('/api/tagging/batch', {
      method: 'POST',
      json: { ids, add_tags: addTags, remove_tags: removeTags, approve },
    })
  }

  deleteAsset(id: number) {
    return this.request<{ ok: true }>('/api/assets/delete', {
      method: 'POST',
      json: { id },
    })
  }

  batchDelete(ids: number[]) {
    return this.request<{ ok: true; deleted_count: number }>('/api/assets/batch-delete', {
      method: 'POST',
      json: { ids },
    })
  }

  analyzeTags(ids: number[]) {
    return this.request<{
      ok: true
      engine: string
      assets: Array<{ id: number; asset_ref: string; suggested_tags?: string[]; confidence?: number }>
    }>('/api/tagging/analyze', {
      method: 'POST',
      json: { ids },
    })
  }

  upload(files: File[], tags: string[]) {
    const body = new FormData()
    for (const file of files) body.append('files', file, file.webkitRelativePath || file.name)
    body.append('tags', tags.join(','))
    return this.request<{ ok: boolean; imported_count: number }>('/api/assets/upload', {
      method: 'POST',
      body,
    })
  }

  importPath(path: string, title: string, caption: string, tags: string[]) {
    return this.request<{ ok: boolean; imported_count?: number }>('/api/assets/import', {
      method: 'POST',
      json: { path, title, caption, tags },
    })
  }

  taxonomy() {
    return this.request<GalleryStatus & { aliases: Array<{ alias: string; canonical_tag: string }> }>('/api/tags')
  }

  diagnosticsQuery(query: string, facets: string[], emotions: EmotionProfile[] = [], excluded: string[] = []) {
    return this.request<{ ok: true } & DiagnosticResult>('/api/diagnostics/query', {
      method: 'POST',
      json: {
        request_id: `web:${Date.now()}`,
        query,
        facets,
        emotions: emotions.map((item, index) => ({
          emotion_tag: item.emotion_tag,
          target_intensity: item.intensity,
          prominence: item.prominence,
          weight: item.prominence === 'primary' || index === 0 ? 1 : 0.55,
        })),
        exclude_asset_refs: excluded,
        limit: 6,
      },
    })
  }

  diagnosticsFeedback(requestId: string, assetRef: string, action: 'useful' | 'negative' | 'skipped', query: string) {
    return this.request<{ ok: true }>('/api/diagnostics/feedback', {
      method: 'POST',
      json: {
        event_id: `web:${requestId}:${assetRef}:${action}`,
        request_id: requestId,
        asset_ref: assetRef,
        action,
        query,
      },
    })
  }

  saveTagDefinition(tag: string, label: string, description: string, aliases: string[]) {
    return this.request<{ ok: true; tag: string }>('/api/tags/definition', {
      method: 'POST',
      json: { tag, label, description, aliases },
    })
  }

  jobs() {
    return this.request<{ ok: true; counts: Record<string, number>; jobs: GalleryJob[] }>('/api/jobs')
  }

  fileUrl(id: number) {
    return `${this.base}/api/assets/file/${id}`
  }

  thumbnailUrl(id: number, size: 320 | 640 = 320) {
    return `${this.base}/api/assets/thumbnail/${id}?size=${size}`
  }

  rebuildThumbnail(id: number, size: 320 | 640 = 320) {
    return this.request<{ ok: true; status: string }>(`/api/assets/thumbnail/${id}/rebuild?size=${size}`, {
      method: 'POST',
    })
  }
}

export const galleryApi = new GalleryApi()
