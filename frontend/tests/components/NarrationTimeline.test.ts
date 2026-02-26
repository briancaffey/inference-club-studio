import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import type {
  NarrationSegment,
  NarrationTranscription,
} from '~/types'
import NarrationTimeline from '~/components/narration-next/NarrationTimeline.vue'

const segments: NarrationSegment[] = [
  {
    id: 1,
    project_id: 'project-1',
    position: 1,
    text: 'First segment',
    sanitized_text: 'First segment',
    service: 'dia',
    status: 'done',
    audio_path: '/tmp/a.wav',
    studio_voice_audio_path: null,
    studio_voice_status: 'not_cleaned',
    studio_voice_error_message: null,
    studio_voice_cleaned_at: null,
    duration_seconds: 2,
    error_message: null,
    quality_score: null,
    needs_review: false,
    is_final: false,
    last_generated_at: null,
    generation_attempts: 1,
    selected_variant_id: null,
    voice_sample_id: null,
    magpie_voice: null,
    original_text: null,
    created_at: '2026-02-26T00:00:00Z',
    updated_at: '2026-02-26T00:00:00Z',
  },
  {
    id: 2,
    project_id: 'project-1',
    position: 2,
    text: 'Second segment',
    sanitized_text: 'Second segment',
    service: 'dia',
    status: 'pending',
    audio_path: null,
    studio_voice_audio_path: null,
    studio_voice_status: 'not_cleaned',
    studio_voice_error_message: null,
    studio_voice_cleaned_at: null,
    duration_seconds: 3,
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
  },
]

const transcriptions: Record<number, NarrationTranscription> = {
  1: {
    id: 11,
    segment_id: 1,
    text: 'First segment',
    words: [{ word: 'First', start: 0, end: 0.3 }],
    created_at: '2026-02-26T00:00:00Z',
  },
}

describe('NarrationTimeline', () => {
  it('renders timeline duration and segment markers', () => {
    const wrapper = mount(NarrationTimeline, {
      props: {
        segments,
        transcriptions,
        playbackSpeed: 1,
        segmentAudioUrl: (segment: NarrationSegment) => `/audio/${segment.id}`,
      },
    })

    expect(wrapper.text()).toContain('0:05')
    expect(wrapper.text()).toContain('1')
    expect(wrapper.text()).toContain('2')
  })

  it('emits playback speed updates', async () => {
    const wrapper = mount(NarrationTimeline, {
      props: {
        segments,
        transcriptions,
        playbackSpeed: 1,
        segmentAudioUrl: (segment: NarrationSegment) => `/audio/${segment.id}`,
      },
    })

    await wrapper.get('input[type="range"]').setValue('1.5')
    expect(wrapper.emitted('update:playbackSpeed')?.[0]).toEqual([1.5])
  })
})
