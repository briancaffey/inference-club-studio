import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import NarrationToolbar from '~/components/narration-next/NarrationToolbar.vue'

function mountToolbar() {
  return mount(NarrationToolbar, {
    props: {
      segmentCount: 6,
      doneCount: 2,
      pendingCount: 3,
      queuedCount: 1,
      generatingCount: 0,
      errorCount: 1,
      totalDuration: '2:10',
      generating: false,
      cancelling: false,
      transcribingAll: false,
      transcribeAllLabel: 'Transcribe All',
      showImport: false,
      showAdd: false,
      showTimeline: false,
      showExport: false,
      hasAudio: true,
      hasSegments: true,
      segmentStatusFilter: 'all',
      segmentSortMode: 'position',
      showFinalSegments: true,
      showNeedsReviewOnly: false,
      filteredCount: 6,
    },
  })
}

describe('NarrationToolbar', () => {
  it('emits action events for top controls', async () => {
    const wrapper = mountToolbar()

    await wrapper.get('[data-testid="toggle-import"]').trigger('click')
    await wrapper.get('[data-testid="generate-all"]').trigger('click')

    expect(wrapper.emitted('toggle-import')).toBeTruthy()
    expect(wrapper.emitted('generate-all')).toBeTruthy()
  })

  it('emits filter and sort updates', async () => {
    const wrapper = mountToolbar()

    await wrapper.get('#segment-filter').setValue('done')
    await wrapper.get('#sort-mode').setValue('recent')

    expect(wrapper.emitted('update:segmentStatusFilter')?.[0]).toEqual(['done'])
    expect(wrapper.emitted('update:segmentSortMode')?.[0]).toEqual(['recent'])
  })

  it('disables export toggle when no audio', () => {
    const wrapper = mount(NarrationToolbar, {
      props: {
        segmentCount: 1,
        doneCount: 0,
        pendingCount: 1,
        queuedCount: 0,
        generatingCount: 0,
        errorCount: 0,
        totalDuration: '0:10',
        generating: false,
        cancelling: false,
        transcribingAll: false,
        transcribeAllLabel: 'Transcribe All',
        showImport: false,
        showAdd: false,
        showTimeline: false,
        showExport: false,
        hasAudio: false,
        hasSegments: true,
        segmentStatusFilter: 'all',
        segmentSortMode: 'position',
        showFinalSegments: true,
        showNeedsReviewOnly: false,
        filteredCount: 1,
      },
    })

    expect(wrapper.get('[data-testid="toggle-export"]').attributes()).toHaveProperty('disabled')
  })
})
