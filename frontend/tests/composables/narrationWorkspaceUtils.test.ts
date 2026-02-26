import { describe, expect, it } from 'vitest'
import type { NarrationSegment } from '~/types'
import {
  filterSegments,
  formatDuration,
  resolveSegmentDisplayStatus,
  sortSegments,
} from '~/composables/narration-next/narrationWorkspaceUtils'

function makeSegment(overrides: Partial<NarrationSegment>): NarrationSegment {
  return {
    id: 1,
    project_id: 'project-1',
    position: 1,
    text: 'Example segment text',
    sanitized_text: 'Example segment text',
    service: 'dia',
    status: 'pending',
    audio_path: null,
    studio_voice_audio_path: null,
    studio_voice_status: 'not_cleaned',
    studio_voice_error_message: null,
    studio_voice_cleaned_at: null,
    duration_seconds: null,
    error_message: null,
    quality_score: null,
    needs_review: false,
    is_final: false,
    last_generated_at: null,
    generation_attempts: 0,
    selected_variant_id: null,
    voice_sample_id: null,
    magpie_voice: null,
    original_text: null,
    created_at: '2026-02-26T00:00:00Z',
    updated_at: '2026-02-26T00:00:00Z',
    ...overrides,
  }
}

describe('narrationWorkspaceUtils', () => {
  it('formats duration in minutes and seconds', () => {
    expect(formatDuration(0)).toBe('0:00')
    expect(formatDuration(65)).toBe('1:05')
  })

  it('sorts by position by default', () => {
    const segments = [
      makeSegment({ id: 10, position: 3 }),
      makeSegment({ id: 11, position: 1 }),
      makeSegment({ id: 12, position: 2 }),
    ]

    const sorted = sortSegments(segments)
    expect(sorted.map(segment => segment.position)).toEqual([1, 2, 3])
  })

  it('sorts by most recent generated timestamp when requested', () => {
    const segments = [
      makeSegment({ id: 10, position: 1, last_generated_at: '2026-02-20T00:00:00Z' }),
      makeSegment({ id: 11, position: 2, last_generated_at: '2026-02-26T00:00:00Z' }),
      makeSegment({ id: 12, position: 3, last_generated_at: null }),
    ]

    const sorted = sortSegments(segments, 'recent')
    expect(sorted.map(segment => segment.id)).toEqual([11, 10, 12])
  })

  it('treats pending segments as queued when queued set contains the id', () => {
    const segment = makeSegment({ id: 42, status: 'pending' })
    const queued = new Set<number>([42])

    expect(resolveSegmentDisplayStatus(segment, queued)).toBe('queued')
  })

  it('applies status and flag filters together', () => {
    const segments = [
      makeSegment({ id: 1, position: 1, status: 'done', needs_review: true }),
      makeSegment({ id: 2, position: 2, status: 'done', is_final: true, needs_review: false }),
      makeSegment({ id: 3, position: 3, status: 'error', needs_review: true }),
    ]

    const filtered = filterSegments({
      segments,
      queuedIds: new Set<number>(),
      statusFilter: 'done',
      sortMode: 'position',
      showFinalSegments: false,
      showNeedsReviewOnly: true,
    })

    expect(filtered.map(segment => segment.id)).toEqual([1])
  })
})
