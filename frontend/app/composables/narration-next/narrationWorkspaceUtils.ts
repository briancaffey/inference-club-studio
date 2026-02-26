import type { NarrationSegment } from '~/types'

export type SegmentStatusFilter = 'all' | 'pending' | 'queued' | 'generating' | 'done' | 'error'
export type SegmentSortMode = 'position' | 'recent'
export type SegmentDisplayStatus = Exclude<SegmentStatusFilter, 'all'> | string

export function formatDuration(seconds: number) {
  if (!seconds || Number.isNaN(seconds)) return '0:00'
  const mins = Math.floor(seconds / 60)
  const secs = Math.floor(seconds % 60)
  return `${mins}:${secs.toString().padStart(2, '0')}`
}

export function estimateDurationFromText(text: string) {
  const normalized = text.trim()
  if (!normalized) return 0
  const words = normalized.split(/\s+/).length
  return words / 2.5
}

export function segmentDurationSeconds(segment: NarrationSegment) {
  return segment.duration_seconds || estimateDurationFromText(segment.text)
}

export function segmentGeneratedAtMs(segment: NarrationSegment) {
  if (!segment.last_generated_at) return 0
  const value = Date.parse(segment.last_generated_at)
  return Number.isFinite(value) ? value : 0
}

export function sortSegments(
  list: NarrationSegment[],
  mode: SegmentSortMode = 'position',
) {
  if (mode === 'recent') {
    return [...list].sort((a, b) => {
      const diff = segmentGeneratedAtMs(b) - segmentGeneratedAtMs(a)
      if (diff !== 0) return diff
      return a.position - b.position
    })
  }

  return [...list].sort((a, b) => a.position - b.position)
}

export function resolveSegmentDisplayStatus(
  segment: NarrationSegment,
  queuedIds: Set<number>,
): SegmentDisplayStatus {
  if (segment.status === 'generating') return 'generating'
  if (segment.status === 'queued') return 'queued'
  if (queuedIds.has(segment.id)) return 'queued'
  return segment.status
}

export function filterSegments(options: {
  segments: NarrationSegment[]
  queuedIds: Set<number>
  statusFilter: SegmentStatusFilter
  sortMode: SegmentSortMode
  showFinalSegments: boolean
  showNeedsReviewOnly: boolean
}) {
  const statusFiltered = options.statusFilter === 'all'
    ? options.segments
    : options.segments.filter(segment => (
        resolveSegmentDisplayStatus(segment, options.queuedIds) === options.statusFilter
      ))

  const finalFiltered = options.showFinalSegments
    ? statusFiltered
    : statusFiltered.filter(segment => !segment.is_final)

  const reviewFiltered = options.showNeedsReviewOnly
    ? finalFiltered.filter(segment => segment.needs_review)
    : finalFiltered

  return sortSegments(reviewFiltered, options.sortMode)
}
