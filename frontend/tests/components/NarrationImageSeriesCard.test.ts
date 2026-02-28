import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import type { NarrationImageSeries } from '~/types'
import NarrationImageSeriesCard from '~/components/narration-next/NarrationImageSeriesCard.vue'

const series: NarrationImageSeries = {
  id: 'series-1',
  segment_id: 22,
  name: 'Classroom branch',
  source_prompt: 'student in classroom',
  plan_json: null,
  status: 'completed',
  error_message: null,
  queued_at: null,
  started_at: null,
  completed_at: '2026-02-26T00:00:00Z',
  created_at: '2026-02-26T00:00:00Z',
  updated_at: '2026-02-26T00:00:00Z',
  frames: [
    {
      id: 'frame-root',
      series_id: 'series-1',
      parent_frame_id: null,
      step_key: 'step_1',
      step_order: 1,
      is_fork: false,
      prompt: 'A boy is sitting in a classroom.',
      mode: 'text_to_image',
      status: 'completed',
      width: 1024,
      height: 1024,
      num_steps: 16,
      cfg_scale: 1,
      seed: -1,
      invokeai_reference_image_name: null,
      invokeai_generated_image_name: 'root_image',
      actual_seed: 11,
      output_image_path: '/app/media/abc.png',
      error_message: null,
      created_at: '2026-02-26T00:00:00Z',
      updated_at: '2026-02-26T00:00:00Z',
    },
  ],
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
    listForSegment: vi.fn(() => [series]),
    latestPreviewFrames: vi.fn(() => series.frames),
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
    suggestPrompts: vi.fn(async () => ['The boy is using a laptop']),
  }
}

describe('NarrationImageSeriesCard', () => {
  it('adds a new frame from composer controls', async () => {
    const controller = buildController()
    const wrapper = mount(NarrationImageSeriesCard, {
      props: {
        segmentId: 22,
        series,
        controller,
      },
    })

    await wrapper.get('button').trigger('click') // expand
    await wrapper.get('textarea[placeholder="Prompt for next frame..."]').setValue('The boy wears a baseball cap')
    await wrapper.get('button.bg-primary').trigger('click')

    expect(controller.addFrame).toHaveBeenCalledWith(22, 'series-1', {
      prompt: 'The boy wears a baseball cap',
      parentFrameId: null,
      isFork: false,
      mode: 'text_to_image',
    })
  })

  it('requests branch regeneration for a frame', async () => {
    const controller = buildController()
    const wrapper = mount(NarrationImageSeriesCard, {
      props: {
        segmentId: 22,
        series,
        controller,
      },
    })

    await wrapper.get('button').trigger('click') // expand
    const regenBranchButton = wrapper.findAll('button').find(button => button.text() === 'Regen Branch')
    expect(regenBranchButton).toBeTruthy()
    await regenBranchButton!.trigger('click')

    expect(controller.regenerateFrame).toHaveBeenCalledWith(22, 'series-1', 'frame-root', {
      includeDescendants: true,
      autoGenerate: true,
    })
  })
})
