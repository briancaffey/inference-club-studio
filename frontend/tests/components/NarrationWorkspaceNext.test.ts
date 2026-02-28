import { mount } from '@vue/test-utils'
import { computed, reactive, ref } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { NarrationSegment } from '~/types'
import NarrationWorkspaceNext from '~/components/NarrationWorkspaceNext.vue'

const sampleSegment: NarrationSegment = {
  id: 1,
  project_id: 'project-1',
  position: 1,
  text: 'Test segment text',
  sanitized_text: 'Test segment text',
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
}

const generateAll = vi.fn()
const retryFailed = vi.fn()
const transcribeAll = vi.fn()
const cancelGeneration = vi.fn()
const importScript = vi.fn()
const addSegment = vi.fn()
const togglePanel = vi.fn()

const mockTrim = {
  expandedTrimSegmentId: ref<number | null>(null),
  trimRangeLabel: ref('Select deadspace to remove'),
  trimSelectionArmed: ref(false),
  trimWaveformLoading: ref(false),
  trimWaveformError: ref(''),
  hasTrimSelection: ref(false),
  trimApplying: ref(false),
  trimDecodedBuffer: ref<AudioBuffer | null>(null),
  trimWaveformData: ref<Float32Array | null>(null),
  trimSegmentId: ref<number | null>(null),
  trimSelectionStart: ref(0),
  trimSelectionEnd: ref(0),
  trimSelectionDuration: ref(0),
  trimAudioDuration: ref(1000),
  segmentHasTrimmableAudio: vi.fn(() => false),
  segmentNeedsTrim: vi.fn(() => false),
  toggleTrim: vi.fn(),
  beginTrimSelection: vi.fn(),
  clearTrimSelection: vi.fn(),
  cancelTrimDeadspace: vi.fn(),
  onTrimWaveformPointerDown: vi.fn(),
  previewTrim: vi.fn(),
  applyTrim: vi.fn(),
  loadTrimWaveform: vi.fn(),
  regenerateTrimWaveform: vi.fn(),
}

const mockWorkspace = {
  loading: ref(false),
  error: ref<string | null>(null),
  status: ref(''),

  segments: ref<NarrationSegment[]>([sampleSegment]),
  transcriptions: reactive({}),
  transcribing: reactive<Record<number, boolean>>({}),
  audioVersion: reactive<Record<number, number>>({}),
  queuedSegmentIds: reactive(new Set<number>()),

  editingId: ref<number | null>(null),
  editText: ref(''),
  expandedTranscript: ref<number | null>(null),
  regenText: reactive<Record<number, string>>({}),

  showImport: ref(false),
  showAdd: ref(false),
  showTimeline: ref(false),
  showExport: ref(false),

  importText: ref(''),
  importService: ref<'dia' | 'magpie'>('dia'),
  addText: ref(''),
  addService: ref<'dia' | 'magpie'>('dia'),

  exportFormat: ref<'wav' | 'mp3'>('wav'),
  exportGapMs: ref(750),
  exportFadeMs: ref(50),
  exportNormalize: ref(true),

  generating: ref(false),
  cancelling: ref(false),
  genIndex: ref(0),
  genTotal: ref(0),
  genEstimate: ref<number | null>(null),

  segmentStatusFilter: ref<'all' | 'pending' | 'queued' | 'generating' | 'done' | 'error'>('all'),
  segmentSortMode: ref<'position' | 'recent'>('position'),
  showFinalSegments: ref(true),
  showNeedsReviewOnly: ref(false),
  transcribeAllProgress: ref<{ done: number; total: number } | null>(null),

  pendingCount: computed(() => 1),
  queuedCount: computed(() => 0),
  generatingCount: computed(() => 0),
  doneCount: computed(() => 0),
  errorCount: computed(() => 1),

  filteredSegments: computed(() => mockWorkspace.segments.value),
  hasAudio: computed(() => true),
  genProgress: computed(() => 0),
  totalDuration: computed(() => '0:04'),

  segmentAudioUrl: vi.fn(() => '/audio'),
  segmentCleanedAudioUrl: vi.fn(() => '/audio/cleaned'),
  segmentPreferredAudioUrl: vi.fn(() => '/audio'),

  fetchSegments: vi.fn(),
  fetchProjectTranscriptions: vi.fn(),
  refreshWorkspace: vi.fn(),

  addSegment,
  importScript,

  startEdit: vi.fn(),
  cancelEdit: vi.fn(),
  saveEdit: vi.fn(),
  updateSegmentService: vi.fn(),
  moveSegment: vi.fn(),
  deleteSegment: vi.fn(),
  clearAllSegments: vi.fn(),

  toggleFinal: vi.fn(),
  clearNeedsReview: vi.fn(),
  markSegmentDone: vi.fn(),

  generateOne: vi.fn(),
  regenerate: vi.fn(),
  generateAll,
  retryFailed,
  cancelGeneration,

  transcribeSegment: vi.fn(),
  deleteTranscription: vi.fn(),
  transcribeAll,
  toggleTranscript: vi.fn(),

  exportAudio: vi.fn(),
  exportAudioZip: vi.fn(),

  resolveSegmentDisplayStatus: vi.fn(() => 'pending'),
}

const mockImageSequences = {
  mediaUrl: vi.fn((path: string | null) => path),
  isPanelOpen: vi.fn(() => false),
  openPanel: vi.fn(),
  closePanel: vi.fn(),
  togglePanel,
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
  refreshSegment: vi.fn(),
  createManualSeries: vi.fn(),
  createAutoSeries: vi.fn(),
  queueSeries: vi.fn(),
  deleteSeries: vi.fn(),
  addFrame: vi.fn(),
  regenerateFrame: vi.fn(),
  suggestPrompts: vi.fn(async () => []),
}

vi.mock('~/composables/narration-next/useNarrationWorkspaceNext', () => ({
  useNarrationWorkspaceNext: vi.fn(() => mockWorkspace),
}))
vi.mock('~/composables/narration-next/useNarrationTrimNext', () => ({
  useNarrationTrimNext: vi.fn(() => mockTrim),
}))
vi.mock('~/composables/narration-next/useNarrationImageSequences', () => ({
  useNarrationImageSequences: vi.fn(() => mockImageSequences),
}))

describe('NarrationWorkspaceNext', () => {
  beforeEach(() => {
    generateAll.mockReset()
    retryFailed.mockReset()
    transcribeAll.mockReset()
    cancelGeneration.mockReset()
    importScript.mockReset()
    addSegment.mockReset()
    togglePanel.mockReset()
    mockImageSequences.ensureSegmentLoaded.mockReset()
    mockImageSequences.latestPreviewFrames.mockReset()
    mockImageSequences.latestPreviewFrames.mockReturnValue([])

    mockWorkspace.showImport.value = false
    mockWorkspace.showAdd.value = false
    mockWorkspace.importText.value = ''
    mockWorkspace.addText.value = ''
  })

  it('renders workspace title and segment text', () => {
    const wrapper = mount(NarrationWorkspaceNext, {
      props: { projectId: 'project-1' },
    })

    expect(wrapper.text()).toContain('Narration Workspace Next')
    expect(wrapper.text()).toContain('Test segment text')
  })

  it('wires toolbar actions to workspace methods', async () => {
    const wrapper = mount(NarrationWorkspaceNext, {
      props: { projectId: 'project-1' },
    })

    await wrapper.get('[data-testid="generate-all"]').trigger('click')
    await wrapper.get('[data-testid="retry-failed"]').trigger('click')
    await wrapper.get('[data-testid="transcribe-all"]').trigger('click')

    expect(generateAll).toHaveBeenCalledTimes(1)
    expect(retryFailed).toHaveBeenCalledTimes(1)
    expect(transcribeAll).toHaveBeenCalledTimes(1)
  })

  it('wires image panel toggle to image sequence controller', async () => {
    const wrapper = mount(NarrationWorkspaceNext, {
      props: { projectId: 'project-1' },
    })

    await wrapper.get('[data-testid="toggle-image-panel"]').trigger('click')
    expect(togglePanel).toHaveBeenCalledWith(sampleSegment.id)
  })

  it('prefetches image sequences for visible segments', () => {
    mount(NarrationWorkspaceNext, {
      props: { projectId: 'project-1' },
    })

    expect(mockImageSequences.ensureSegmentLoaded).toHaveBeenCalledWith(sampleSegment.id)
  })

  it('opens import and add panels and triggers actions', async () => {
    const wrapper = mount(NarrationWorkspaceNext, {
      props: { projectId: 'project-1' },
    })

    await wrapper.get('[data-testid="toggle-import"]').trigger('click')
    await wrapper.get('[data-testid="import-text"]').setValue('Line one\nLine two')
    await wrapper.get('[data-testid="import-script"]').trigger('click')

    await wrapper.get('[data-testid="toggle-add"]').trigger('click')
    await wrapper.get('textarea[placeholder="Segment text"]').setValue('A new segment')
    await wrapper.get('[data-testid="add-segment"]').trigger('click')

    expect(importScript).toHaveBeenCalledTimes(1)
    expect(addSegment).toHaveBeenCalledTimes(1)
  })
})
