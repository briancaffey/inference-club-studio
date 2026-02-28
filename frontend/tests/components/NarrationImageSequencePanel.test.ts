import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import type { NarrationSegment } from '~/types'
import NarrationImageSequencePanel from '~/components/narration-next/NarrationImageSequencePanel.vue'

const segment: NarrationSegment = {
  id: 12,
  project_id: 'project-1',
  position: 3,
  text: 'A student in a classroom',
  sanitized_text: 'A student in a classroom',
  service: 'dia',
  status: 'done',
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
}

function buildController() {
  return {
    mediaUrl: (path: string | null) => path,
    isPanelOpen: vi.fn(() => true),
    openPanel: vi.fn(),
    closePanel: vi.fn(),
    togglePanel: vi.fn(),
    ensureSegmentLoaded: vi.fn(async () => {}),
    clearSegment: vi.fn(),
    clearAll: vi.fn(),
    listForSegment: vi.fn(() => []),
    latestPreviewFrames: vi.fn(() => []),
    isLoadingSegment: vi.fn(() => false),
    segmentError: vi.fn(() => null),
    isCreatingSegment: vi.fn(() => false),
    isSeriesBusy: vi.fn(() => false),
    isSeriesSuggesting: vi.fn(() => false),
    refreshSegment: vi.fn(async () => {}),
    createManualSeries: vi.fn(async () => ({})),
    createAutoSeries: vi.fn(async () => ({})),
    queueSeries: vi.fn(async () => ({})),
    deleteSeries: vi.fn(async () => {}),
    addFrame: vi.fn(async () => {}),
    regenerateFrame: vi.fn(async () => ({})),
    suggestPrompts: vi.fn(async () => []),
  }
}

describe('NarrationImageSequencePanel', () => {
  it('creates a manual sequence from quick-start form', async () => {
    const controller = buildController()
    const wrapper = mount(NarrationImageSequencePanel, {
      props: {
        segment,
        controller,
      },
    })

    const textareas = wrapper.findAll('textarea')
    await wrapper.get('input[placeholder="Series name (optional)"]').setValue('Bench test')
    await textareas[0].setValue('A man sitting on a park bench, photoreal')
    await wrapper.get('form').trigger('submit.prevent')

    expect(controller.createManualSeries).toHaveBeenCalledWith(segment.id, {
      name: 'Bench test',
      initialPrompt: 'A man sitting on a park bench, photoreal',
      autoGenerate: true,
    })
  })

  it('creates an auto-planned sequence from AI form', async () => {
    const controller = buildController()
    const wrapper = mount(NarrationImageSequencePanel, {
      props: {
        segment,
        controller,
      },
    })

    const forms = wrapper.findAll('form')
    const textareas = wrapper.findAll('textarea')
    const targetInputs = wrapper.findAll('input[type="number"]')

    await wrapper.findAll('input[placeholder="Series name (optional)"]')[1].setValue('Anime branch')
    await textareas[1].setValue('Keep scene continuity, then shift style to anime.')
    await targetInputs[0].setValue('5')
    await forms[1].trigger('submit.prevent')

    expect(controller.createAutoSeries).toHaveBeenCalledWith(segment.id, {
      name: 'Anime branch',
      creativeDirection: 'Keep scene continuity, then shift style to anime.',
      targetImages: 5,
    })
  })
})
