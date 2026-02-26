import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import type { NarrationSegment, NarrationTranscription } from '~/types'
import NarrationSegmentCard from '~/components/narration-next/NarrationSegmentCard.vue'

const segment: NarrationSegment = {
  id: 7,
  project_id: 'project-1',
  position: 2,
  text: 'Hello from narration segment',
  sanitized_text: 'Hello from narration segment',
  service: 'dia',
  status: 'done',
  audio_path: '/tmp/audio.wav',
  studio_voice_audio_path: null,
  studio_voice_status: 'not_cleaned',
  studio_voice_error_message: null,
  studio_voice_cleaned_at: null,
  duration_seconds: 2.1,
  error_message: null,
  quality_score: null,
  needs_review: true,
  is_final: false,
  last_generated_at: '2026-02-26T00:00:00Z',
  generation_attempts: 1,
  selected_variant_id: null,
  voice_sample_id: null,
  magpie_voice: null,
  original_text: null,
  created_at: '2026-02-26T00:00:00Z',
  updated_at: '2026-02-26T00:00:00Z',
}

const transcription: NarrationTranscription = {
  id: 10,
  segment_id: segment.id,
  text: 'Hello from narration segment',
  words: [
    { word: 'Hello', start: 0, end: 0.35 },
    { word: 'from', start: 0.35, end: 0.5 },
  ],
  created_at: '2026-02-26T00:00:00Z',
}

const baseProps = {
  segment,
  displayStatus: 'done',
  editing: false,
  editText: segment.text,
  regenText: '',
  transcribing: false,
  transcription,
  expandedTranscript: false,
  generating: false,
  audioUrl: '/audio',
  cleanedAudioUrl: null,
  activeWordIdx: -1,
  canTrim: true,
  trimOpen: false,
  trimRangeLabel: '',
  trimSelectionArmed: false,
  trimWaveformLoading: false,
  trimWaveformError: '',
  hasTrimSelection: false,
  trimApplying: false,
  canPreviewTrim: false,
  trimWaveformReady: false,
  trimSelectionStart: 0,
  trimSelectionEnd: 0,
  trimSelectionDuration: 0,
  trimAudioDuration: 1000,
  trimSuggested: false,
}

describe('NarrationSegmentCard', () => {
  it('emits edit and generate actions', async () => {
    const wrapper = mount(NarrationSegmentCard, {
      props: baseProps,
    })

    await wrapper.get('[data-testid="start-edit"]').trigger('click')
    await wrapper.get('[data-testid="generate"]').trigger('click')

    expect(wrapper.emitted('start-edit')?.[0]).toEqual([segment])
    expect(wrapper.emitted('generate')?.[0]).toEqual([segment.id])
  })

  it('emits edit text updates and save when in editing mode', async () => {
    const wrapper = mount(NarrationSegmentCard, {
      props: {
        ...baseProps,
        editing: true,
      },
    })

    await wrapper.get('[data-testid="edit-text"]').setValue('Updated text')
    await wrapper.get('[data-testid="save-edit"]').trigger('click')

    expect(wrapper.emitted('update:editText')?.[0]).toEqual(['Updated text'])
    expect(wrapper.emitted('save-edit')?.[0]).toEqual([segment.id])
  })

  it('emits seek-word when transcript token is clicked', async () => {
    const wrapper = mount(NarrationSegmentCard, {
      props: {
        ...baseProps,
        expandedTranscript: true,
      },
    })

    const wordButton = wrapper.findAll('button').find(button => button.text() === 'Hello')
    expect(wordButton).toBeTruthy()
    await wordButton!.trigger('click')

    expect(wrapper.emitted('seek-word')?.[0]).toEqual([segment.id, 0])
  })

  it('emits toggle-trim from dropdown action menu', async () => {
    const wrapper = mount(NarrationSegmentCard, {
      props: baseProps,
    })

    await wrapper.get('[data-testid="segment-action-menu"]').setValue('trim')

    expect(wrapper.emitted('toggle-trim')?.[0]).toEqual([segment.id])
  })
})
