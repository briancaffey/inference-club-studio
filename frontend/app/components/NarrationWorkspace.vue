<script setup lang="ts">
import {
  AlertCircle,
  CheckCircle2,
  Loader2,
  Mic2,
  Pause,
  Play,
  Plus,
  RefreshCw,
  Scissors,
  Upload,
  Waves,
  XCircle,
} from 'lucide-vue-next'
import type {
  Project,
  NarrationSegment,
  NarrationService,
  NarrationTranscription,
  NarrationVariant,
  NarrationVoiceSampleDraft,
  NarrationVoiceSample,
  NarrationSegmentSplitPreview,
  NarrationSegmentSplitResult,
} from '~/types'

interface ArticleChunk {
  raw: string
  segments: string[]
  processed: boolean
  error: boolean
  retrying: boolean
}

interface TranscribeAllProgress {
  done: number
  total: number
}

interface WaveformLoadOptions {
  force?: boolean
}

interface SpeechBounds {
  startMs: number
  endMs: number
}

interface WaveformMeta {
  durationMs: number
  speechBounds: SpeechBounds | null
}

interface TrimResponse {
  segment: NarrationSegment
  transcription: NarrationTranscription | null
}

interface SegmentWaveformResponse {
  segment_id: number
  source: 'original' | 'cleaned'
  audio_path: string
  points: number
  duration_ms: number
  samples: number[]
}

type TrimHandle = 'start' | 'end'
type SegmentStatusFilter = 'all' | 'pending' | 'queued' | 'generating' | 'done' | 'error'
type SegmentSortMode = 'position' | 'recent'

const props = defineProps<{
  projectId: string
}>()

const { baseURL } = useApi()

const loading = ref(false)
const error = ref<string | null>(null)
const status = ref('')

const segments = ref<NarrationSegment[]>([])
const variantsMap = reactive<Record<number, NarrationVariant[]>>({})
const transcriptions = reactive<Record<number, NarrationTranscription>>({})
const transcribing = reactive<Record<number, boolean>>({})
const audioVersion = reactive<Record<number, number>>({})
const waveformData = reactive<Record<number, Float32Array>>({})
const waveformLoading = reactive<Record<number, boolean>>({})
const waveformMeta = reactive<Record<number, WaveformMeta>>({})

const editingId = ref<number | null>(null)
const editText = ref('')
const expandedVariants = ref<number | null>(null)
const expandedTranscript = ref<number | null>(null)
const expandedTrim = ref<number | null>(null)
const regenText = reactive<Record<number, string>>({})
const confirmClear = ref(false)
const splitSegmentId = ref<number | null>(null)
const splitTargetWords = ref(32)
const splitPreview = ref<NarrationSegmentSplitPreview | null>(null)
const splitPreviewLoading = ref(false)
const splitApplying = ref(false)

const showImport = ref(false)
const importMode = ref<'script' | 'article'>('script')
const importText = ref('')
const importService = ref<NarrationService>('dia')
const articleText = ref('')
const articleChunks = ref<ArticleChunk[]>([])
const articleProcessing = ref(false)
const articleStatus = ref('')

const showAdd = ref(false)
const addText = ref('')
const addService = ref<NarrationService>('dia')
const insertAtPosition = ref<number | null>(null)
const insertText = ref('')
const insertService = ref<NarrationService>('dia')

const showScriptEditor = ref(false)
const scriptText = ref('')
const scriptSyncing = ref(false)
const scriptSyncStatus = ref('')

const showVoices = ref(false)
const voiceSamples = ref<NarrationVoiceSample[]>([])
const voiceSampleTranscriptDrafts = reactive<Record<number, string>>({})
const voiceSampleSaving = reactive<Record<number, boolean>>({})
const magpieVoices = ref<string[]>([])
const voiceName = ref('')
const voiceClipInput = ref<HTMLInputElement | null>(null)
const voiceClipFile = ref<File | null>(null)
const voiceDraft = ref<NarrationVoiceSampleDraft | null>(null)
const voiceDraftTranscript = ref('')
const voiceDraftTrimStartMs = ref(0)
const voiceDraftTrimEndMs = ref(50)
const voiceDraftAudioDurationMs = ref<number | null>(null)
const voiceDraftWaveformData = ref<Float32Array | null>(null)
const voiceDraftDragging = ref<TrimHandle | null>(null)
const voiceDraftBusy = ref(false)
const voiceDraftAudioVersion = ref(0)
const globalVoiceSampleId = ref<number | null>(null)
const globalMagpieVoice = ref('')
const projectMetadata = ref<Record<string, unknown>>({})
const applyingProjectVoiceDefaults = ref(false)

const showExport = ref(false)
const exportFormat = ref<'wav' | 'mp3'>('wav')
const exportGapMs = ref(750)
const exportFadeMs = ref(50)
const exportNormalize = ref(true)

const showTimeline = ref(false)
const playbackSpeed = ref(1)
const timelineZoomLevel = ref(1)
const timelineAudioPlayer = ref<HTMLAudioElement | null>(null)
const timelineScrollEl = ref<HTMLElement | null>(null)
const wordTrackScrollEl = ref<HTMLElement | null>(null)
const timelinePlayingIdx = ref(-1)
const timelineCurrentTime = ref(0)
const timelineIsPlaying = ref(false)
const timelineScrollLeft = ref(0)
const timelineContainerWidth = ref(0)

const transcribeAllProgress = ref<TranscribeAllProgress | null>(null)

const trimStart = ref(0)
const trimEnd = ref(0)
const trimWaveformData = ref<Float32Array | null>(null)
const trimAudioDuration = ref(1)
const trimApplying = ref(false)
const trimSelectionArmed = ref(false)
const trimSelecting = ref(false)
const trimSelectionAnchorMs = ref(0)
const trimSegmentId = ref<number | null>(null)
const trimDecodedBuffer = ref<AudioBuffer | null>(null)
const trimWaveformLoading = ref(false)
const trimWaveformError = ref('')

const generating = ref(false)
const cancelling = ref(false)
const studioVoiceCleaningAll = ref(false)
const genIndex = ref(0)
const genTotal = ref(0)
const genEstimate = ref<number | null>(null)
const queuedSegmentIds = reactive(new Set<number>())
const collapsedSegmentIds = reactive(new Set<number>())
const segmentStatusFilter = ref<SegmentStatusFilter>('all')
const segmentSortMode = ref<SegmentSortMode>('position')
const doneTrimSuggestedOnly = ref(false)
const showFinalSegments = ref(true)
const showNeedsReviewOnly = ref(false)

let ws: WebSocket | null = null
let wsReconnectTimer: ReturnType<typeof setTimeout> | null = null
let fetchSegmentsRequestId = 0
let timelineAnimFrame: number | null = null
let timelineResizeObserver: ResizeObserver | null = null
let audioContext: AudioContext | null = null
let trimPreviewSource: AudioBufferSourceNode | null = null
let wordTrackScrollTarget = 0
let wordTrackAnimating = false
let projectVoiceDefaultsRequestId = 0
let trimWaveformRequestId = 0

const MIN_TIMELINE_SEGMENT_PX = 56
const MIN_TRIM_GAP_MS = 50
const MIN_TIMELINE_ZOOM_LEVEL = 0.25
const MAX_TIMELINE_ZOOM_LEVEL = 4
const DEFAULT_SPLIT_TARGET_WORDS = 32
const MIN_SPLIT_TARGET_WORDS = 8
const MAX_SPLIT_TARGET_WORDS = 120
const PROJECT_NARRATION_DEFAULTS_KEY = 'narration_defaults'
const PROJECT_DIA_DEFAULT_VOICE_KEY = 'dia_voice_sample_id'
const PROJECT_MAGPIE_DEFAULT_VOICE_KEY = 'magpie_voice'

const pendingCount = computed(() => segments.value.filter(segment => segmentDisplayStatus(segment) === 'pending').length)
const queuedCount = computed(() => segments.value.filter(segment => segmentDisplayStatus(segment) === 'queued').length)
const generatingCount = computed(() => segments.value.filter(segment => segmentDisplayStatus(segment) === 'generating').length)
const doneCount = computed(() => segments.value.filter(segment => segmentDisplayStatus(segment) === 'done').length)
const errorCount = computed(() => segments.value.filter(segment => segmentDisplayStatus(segment) === 'error').length)
const studioVoiceCleanedCount = computed(() => (
  segments.value.filter(segment => !!segment.studio_voice_audio_path).length
))
const studioVoicePendingCount = computed(() => (
  segments.value.filter(segment => !!segment.audio_path && !segment.studio_voice_audio_path).length
))
const studioVoiceCleanAllLabel = computed(() => {
  if (studioVoiceCleaningAll.value) return 'Queueing Studio Voice...'
  if (!studioVoicePendingCount.value) return 'Clean All (Studio Voice)'
  return `Clean All (Studio Voice) ${studioVoicePendingCount.value}`
})
const trimSuggestedDoneCount = computed(() => (
  segments.value.filter(segment => segmentDisplayStatus(segment) === 'done' && segmentNeedsTrim(segment)).length
))
const filteredSegments = computed(() => {
  const statusFiltered = segmentStatusFilter.value === 'all'
    ? segments.value
    : segments.value.filter(segment => segmentDisplayStatus(segment) === segmentStatusFilter.value)

  const finalFiltered = showFinalSegments.value
    ? statusFiltered
    : statusFiltered.filter(segment => !segment.is_final)

  const reviewFiltered = showNeedsReviewOnly.value
    ? finalFiltered.filter(segment => segment.needs_review)
    : finalFiltered

  if (segmentStatusFilter.value === 'done' && doneTrimSuggestedOnly.value) {
    return sortSegments(
      reviewFiltered.filter(segment => segmentNeedsTrim(segment)),
      segmentSortMode.value,
    )
  }

  return sortSegments(reviewFiltered, segmentSortMode.value)
})
const hasCollapsedFilteredSegments = computed(() => (
  filteredSegments.value.some(segment => collapsedSegmentIds.has(segment.id))
))
const hasExpandedFilteredSegments = computed(() => (
  filteredSegments.value.some(segment => !collapsedSegmentIds.has(segment.id))
))
const hasAudio = computed(() => doneCount.value > 0)
const genProgress = computed(() => {
  if (!genTotal.value) return 0
  return Math.round((genIndex.value / genTotal.value) * 100)
})
const totalDuration = computed(() => {
  const total = segments.value.reduce((sum, segment) => sum + (segment.duration_seconds || 0), 0)
  return formatDuration(total)
})
const timelineTotalSeconds = computed(() => segments.value.reduce((sum, segment) => sum + segmentDurationSeconds(segment), 0))
const timelineOffsets = computed(() => {
  const offsets: number[] = []
  let acc = 0
  for (const segment of segments.value) {
    offsets.push(acc)
    acc += segmentDurationSeconds(segment)
  }
  return offsets
})
const timelineWidths = computed(() => {
  const total = timelineTotalSeconds.value
  if (!total) return segments.value.map(() => 0)
  return segments.value.map(segment => (segmentDurationSeconds(segment) / total) * 100)
})
const timelineCursorPercent = computed(() => {
  const total = timelineTotalSeconds.value
  if (!total || timelinePlayingIdx.value < 0) return 0
  const offset = timelineOffsets.value[timelinePlayingIdx.value] || 0
  const percent = ((offset + timelineCurrentTime.value) / total) * 100
  return Math.max(0, Math.min(100, percent))
})
const timelineHasDoneSegments = computed(() => (
  segments.value.some(segment => segment.status === 'done' && timelineSegmentHasAudio(segment))
))
const autoTimelineZoom = computed(() => {
  const count = segments.value.length
  if (!count) return 1
  const containerWidth = timelineContainerWidth.value || 680
  const neededWidth = count * MIN_TIMELINE_SEGMENT_PX
  return Math.max(1, neededWidth / containerWidth)
})
const timelineZoom = computed(() => {
  const scaled = autoTimelineZoom.value * timelineZoomLevel.value
  return Math.max(1, Math.min(24, scaled))
})
const timelineInnerWidth = computed(() => timelineZoom.value * 100)
const timelineViewportRatio = computed(() => Math.min(1, 1 / timelineZoom.value))
const timelineViewportLeft = computed(() => {
  const el = timelineScrollEl.value
  if (!el || el.scrollWidth <= el.clientWidth) return 0
  const maxScroll = el.scrollWidth - el.clientWidth
  if (maxScroll <= 0) return 0
  return timelineScrollLeft.value / maxScroll
})
const trimSelectionStart = computed(() => Math.min(trimStart.value, trimEnd.value))
const trimSelectionEnd = computed(() => Math.max(trimStart.value, trimEnd.value))
const trimSelectionDuration = computed(() => Math.max(0, trimSelectionEnd.value - trimSelectionStart.value))
const hasTrimSelection = computed(() => trimSelectionDuration.value >= MIN_TRIM_GAP_MS)
const trimRangeLabel = computed(() => {
  if (!hasTrimSelection.value) {
    return 'No deadspace selected'
  }
  const startSeconds = (trimSelectionStart.value / 1000).toFixed(2)
  const endSeconds = (trimSelectionEnd.value / 1000).toFixed(2)
  const durationSeconds = (trimSelectionDuration.value / 1000).toFixed(2)
  return `Remove ${startSeconds}s - ${endSeconds}s (${durationSeconds}s)`
})
const voiceDraftDurationMs = computed(() => {
  if (voiceDraftAudioDurationMs.value && voiceDraftAudioDurationMs.value >= MIN_TRIM_GAP_MS) {
    return voiceDraftAudioDurationMs.value
  }
  if (!voiceDraft.value?.duration_seconds) return MIN_TRIM_GAP_MS
  return Math.max(MIN_TRIM_GAP_MS, Math.round(voiceDraft.value.duration_seconds * 1000))
})
const voiceDraftTrimRangeLabel = computed(() => {
  const startSeconds = (voiceDraftTrimStartMs.value / 1000).toFixed(2)
  const endSeconds = (voiceDraftTrimEndMs.value / 1000).toFixed(2)
  const durationSeconds = ((voiceDraftTrimEndMs.value - voiceDraftTrimStartMs.value) / 1000).toFixed(2)
  return `${startSeconds}s - ${endSeconds}s (${durationSeconds}s)`
})
const canFinalizeVoiceDraft = computed(() => !!voiceDraft.value && !!voiceName.value.trim())

const wsUrl = computed(() => {
  try {
    const url = new URL(baseURL)
    url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:'
    url.pathname = '/ws'
    url.search = ''
    return url.toString()
  } catch {
    return null
  }
})

function formatDuration(seconds: number) {
  if (!seconds) return '0:00'
  const mins = Math.floor(seconds / 60)
  const secs = Math.floor(seconds % 60)
  return `${mins}:${secs.toString().padStart(2, '0')}`
}

function segmentPreviewText(text: string, maxWords = 9) {
  const trimmed = text.trim()
  if (!trimmed) return ''
  const words = trimmed.split(/\s+/)
  if (words.length <= maxWords) return trimmed
  return `${words.slice(0, maxWords).join(' ')} ...`
}

function segmentDisplayStatus(segment: NarrationSegment) {
  if (segment.status === 'generating') return 'generating'
  if (segment.status === 'queued') return 'queued'
  if (queuedSegmentIds.has(segment.id)) return 'queued'
  return segment.status
}

function isSegmentCollapsed(segmentId: number) {
  return collapsedSegmentIds.has(segmentId)
}

function toggleSegmentCollapsed(segmentId: number) {
  if (collapsedSegmentIds.has(segmentId)) {
    collapsedSegmentIds.delete(segmentId)
    return
  }
  collapsedSegmentIds.add(segmentId)
}

function collapseFilteredSegments() {
  for (const segment of filteredSegments.value) {
    collapsedSegmentIds.add(segment.id)
  }
}

function expandFilteredSegments() {
  for (const segment of filteredSegments.value) {
    collapsedSegmentIds.delete(segment.id)
  }
}

function statusClass(segmentStatus: string) {
  if (segmentStatus === 'done') return 'bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-300'
  if (segmentStatus === 'generating') return 'bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-300'
  if (segmentStatus === 'queued') return 'bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300'
  if (segmentStatus === 'error') return 'bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300'
  return 'bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300'
}

function studioVoiceStatusLabel(status: string) {
  if (status === 'cleaned') return 'Cleaned'
  if (status === 'unavailable') return 'Unavailable'
  if (status === 'error') return 'Error'
  return 'Not cleaned'
}

function studioVoiceStatusClass(status: string) {
  if (status === 'cleaned') return 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300'
  if (status === 'unavailable') return 'bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300'
  if (status === 'error') return 'bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300'
  return 'bg-slate-100 text-slate-700 dark:bg-slate-900/40 dark:text-slate-300'
}

function estimateDurationFromText(text: string) {
  if (!text.trim()) return 0
  const words = text.trim().split(/\s+/).length
  return words / 2.5
}

function segmentDurationSeconds(segment: NarrationSegment) {
  return segment.duration_seconds || estimateDurationFromText(segment.text)
}

function segmentGeneratedAtMs(segment: NarrationSegment) {
  if (!segment.last_generated_at) return 0
  const timestamp = Date.parse(segment.last_generated_at)
  return Number.isFinite(timestamp) ? timestamp : 0
}

function sortSegments(list: NarrationSegment[], mode: SegmentSortMode = 'position') {
  if (mode === 'recent') {
    return [...list].sort((a, b) => {
      const diff = segmentGeneratedAtMs(b) - segmentGeneratedAtMs(a)
      if (diff !== 0) return diff
      return a.position - b.position
    })
  }
  return [...list].sort((a, b) => a.position - b.position)
}

function clearWaveform(segmentId: number) {
  delete waveformData[segmentId]
  delete waveformLoading[segmentId]
  delete waveformMeta[segmentId]
}

function invalidateSegmentAudio(segmentId: number) {
  audioVersion[segmentId] = (audioVersion[segmentId] || 0) + 1
  clearWaveform(segmentId)
}

function segmentAudioChanged(previous: NarrationSegment, next: NarrationSegment) {
  return (
    previous.audio_path !== next.audio_path
    || previous.studio_voice_audio_path !== next.studio_voice_audio_path
    || previous.studio_voice_status !== next.studio_voice_status
    || previous.duration_seconds !== next.duration_seconds
    || previous.selected_variant_id !== next.selected_variant_id
    || previous.status !== next.status
  )
}

function normalizedSplitTargetWords() {
  const parsed = Number(splitTargetWords.value)
  if (!Number.isFinite(parsed)) {
    splitTargetWords.value = DEFAULT_SPLIT_TARGET_WORDS
    return DEFAULT_SPLIT_TARGET_WORDS
  }
  const rounded = Math.round(parsed)
  const clamped = Math.max(
    MIN_SPLIT_TARGET_WORDS,
    Math.min(MAX_SPLIT_TARGET_WORDS, rounded),
  )
  splitTargetWords.value = clamped
  return clamped
}

function resetSplitState(options: { keepTarget?: boolean } = {}) {
  splitSegmentId.value = null
  splitPreview.value = null
  splitPreviewLoading.value = false
  splitApplying.value = false
  if (!options.keepTarget) {
    splitTargetWords.value = DEFAULT_SPLIT_TARGET_WORDS
  }
}

function setSegments(list: NarrationSegment[]) {
  const previousById = new Map(segments.value.map(segment => [segment.id, segment]))
  const ordered = sortSegments(list)
  const validIds = new Set(ordered.map(segment => segment.id))

  for (const queuedId of [...queuedSegmentIds]) {
    if (!validIds.has(queuedId)) {
      queuedSegmentIds.delete(queuedId)
    }
  }
  for (const collapsedId of [...collapsedSegmentIds]) {
    if (!validIds.has(collapsedId)) {
      collapsedSegmentIds.delete(collapsedId)
    }
  }
  if (splitSegmentId.value !== null && !validIds.has(splitSegmentId.value)) {
    resetSplitState({ keepTarget: true })
  }

  for (const segment of segments.value) {
    if (validIds.has(segment.id)) continue
    delete variantsMap[segment.id]
    delete transcriptions[segment.id]
    delete transcribing[segment.id]
    delete regenText[segment.id]
    delete audioVersion[segment.id]
    clearWaveform(segment.id)
  }

  for (const segment of ordered) {
    const previous = previousById.get(segment.id)
    if (previous && segmentAudioChanged(previous, segment)) {
      invalidateSegmentAudio(segment.id)
      delete transcriptions[segment.id]
    }
    if (segment.status !== 'done' || !timelineSegmentHasAudio(segment)) {
      clearWaveform(segment.id)
      delete transcriptions[segment.id]
    }
  }

  segments.value = ordered

  if (showScriptEditor.value) {
    scriptText.value = segments.value.map(segment => segment.text).join('\n')
  }

  if (timelinePlayingIdx.value >= segments.value.length) {
    stopTimelinePlayback()
  }

  if (showTimeline.value) {
    nextTick(() => {
      for (const segment of segments.value) {
        if (segment.status === 'done' && timelineSegmentHasAudio(segment)) {
          void loadWaveform(segment.id)
        } else {
          drawWaveform(segment.id)
        }
      }
      drawAllWaveforms()
    })
  }
}

function updateSegmentInPlace(segment: NarrationSegment) {
  const index = segments.value.findIndex(item => item.id === segment.id)
  if (index === -1) return

  const previous = segments.value[index]
  const audioChanged = segmentAudioChanged(previous, segment)
  segments.value[index] = segment
  segments.value = sortSegments(segments.value)

  if (audioChanged) {
    invalidateSegmentAudio(segment.id)
    delete transcriptions[segment.id]
  }

  if (showTimeline.value && segment.status === 'done' && timelineSegmentHasAudio(segment)) {
    void loadWaveform(segment.id, { force: audioChanged })
  }
}

function segmentAudioUrl(segmentId: number) {
  return `${baseURL}/api/segments/${segmentId}/audio?v=${audioVersion[segmentId] || 0}`
}

function segmentCleanedAudioUrl(segmentId: number) {
  return `${baseURL}/api/segments/${segmentId}/audio/cleaned?v=${audioVersion[segmentId] || 0}`
}

function timelineSegmentHasAudio(segment: NarrationSegment) {
  return !!segment.studio_voice_audio_path || !!segment.audio_path
}

function segmentHasTrimmableAudio(segment: NarrationSegment) {
  if (!segment.audio_path) return false
  return segment.status === 'done' || segment.status === 'error'
}

function timelineAudioUrl(
  segment: NarrationSegment,
  preferredSource: 'cleaned' | 'original' = 'cleaned',
) {
  if (preferredSource === 'cleaned' && segment.studio_voice_audio_path) {
    return segmentCleanedAudioUrl(segment.id)
  }
  return segmentAudioUrl(segment.id)
}

function variantAudioUrl(variantId: number) {
  return `${baseURL}/api/variants/${variantId}/audio`
}

function variantCleanedAudioUrl(variantId: number) {
  return `${baseURL}/api/variants/${variantId}/audio/cleaned`
}

function voiceSampleAudioUrl(sampleId: number) {
  return `${baseURL}/api/voice-samples/${sampleId}/audio`
}

function voiceSampleDraftAudioUrl(draftId: string) {
  return `${baseURL}/api/voice-samples/drafts/${draftId}/audio?v=${voiceDraftAudioVersion.value}`
}

function asRecord(value: unknown): Record<string, unknown> {
  if (value && typeof value === 'object' && !Array.isArray(value)) {
    return { ...(value as Record<string, unknown>) }
  }
  return {}
}

function parsePositiveInt(value: unknown): number | null {
  if (typeof value === 'number' && Number.isInteger(value) && value > 0) {
    return value
  }
  if (typeof value === 'string') {
    const parsed = Number(value)
    if (Number.isInteger(parsed) && parsed > 0) {
      return parsed
    }
  }
  return null
}

function getProjectDefaultVoiceSampleId(metadata: Record<string, unknown>): number | null {
  const narrationDefaults = asRecord(metadata[PROJECT_NARRATION_DEFAULTS_KEY])
  return parsePositiveInt(narrationDefaults[PROJECT_DIA_DEFAULT_VOICE_KEY])
}

function getProjectDefaultMagpieVoice(metadata: Record<string, unknown>): string {
  const narrationDefaults = asRecord(metadata[PROJECT_NARRATION_DEFAULTS_KEY])
  const magpieVoice = narrationDefaults[PROJECT_MAGPIE_DEFAULT_VOICE_KEY]
  if (typeof magpieVoice === 'string') {
    return magpieVoice.trim()
  }
  return ''
}

async function fetchProjectVoiceDefaults() {
  applyingProjectVoiceDefaults.value = true
  projectMetadata.value = {}
  globalVoiceSampleId.value = null
  globalMagpieVoice.value = ''

  try {
    const project = await $fetch<Project>(`${baseURL}/api/v1/projects/${props.projectId}`)
    const metadata = asRecord(project.metadata)
    projectMetadata.value = metadata
    globalVoiceSampleId.value = getProjectDefaultVoiceSampleId(metadata)
    globalMagpieVoice.value = getProjectDefaultMagpieVoice(metadata)
  } catch {
    projectMetadata.value = {}
    globalVoiceSampleId.value = null
    globalMagpieVoice.value = ''
  } finally {
    applyingProjectVoiceDefaults.value = false
  }
}

async function persistProjectVoiceDefaults() {
  if (applyingProjectVoiceDefaults.value) return

  const narrationDefaults = asRecord(projectMetadata.value[PROJECT_NARRATION_DEFAULTS_KEY])
  narrationDefaults[PROJECT_DIA_DEFAULT_VOICE_KEY] = globalVoiceSampleId.value
  narrationDefaults[PROJECT_MAGPIE_DEFAULT_VOICE_KEY] = globalMagpieVoice.value.trim()

  const nextMetadata: Record<string, unknown> = {
    ...projectMetadata.value,
    [PROJECT_NARRATION_DEFAULTS_KEY]: narrationDefaults,
  }
  projectMetadata.value = nextMetadata

  const requestId = ++projectVoiceDefaultsRequestId
  try {
    await $fetch(`${baseURL}/api/v1/projects/${props.projectId}`, {
      method: 'PATCH',
      body: { metadata: nextMetadata },
    })
  } catch (err: any) {
    if (requestId !== projectVoiceDefaultsRequestId) return
    status.value = err?.data?.detail || 'Failed to save default voices'
  }
}

function getAudioContext() {
  if (!import.meta.client) return null
  if (audioContext) return audioContext

  const win = window as Window & { webkitAudioContext?: typeof AudioContext }
  const AudioContextCtor = win.AudioContext || win.webkitAudioContext
  if (!AudioContextCtor) return null

  audioContext = new AudioContextCtor()
  return audioContext
}

function buildWaveformSamples(raw: Float32Array, points: number) {
  const clampedPoints = Math.max(1, points)
  const blockSize = Math.max(1, Math.floor(raw.length / clampedPoints))
  const samples = new Float32Array(clampedPoints)

  for (let i = 0; i < clampedPoints; i += 1) {
    const start = i * blockSize
    let sum = 0
    for (let j = start; j < start + blockSize && j < raw.length; j += 1) {
      sum += Math.abs(raw[j])
    }
    samples[i] = sum / blockSize
  }

  let max = 0
  for (let i = 0; i < samples.length; i += 1) {
    if (samples[i] > max) max = samples[i]
  }

  if (max > 0) {
    for (let i = 0; i < samples.length; i += 1) {
      samples[i] /= max
    }
  }

  return samples
}

function detectSpeechBounds(samples: Float32Array, durationMs: number): SpeechBounds | null {
  if (!samples.length || durationMs <= 0) return null

  let maxValue = 0
  for (let i = 0; i < samples.length; i += 1) {
    if (samples[i] > maxValue) maxValue = samples[i]
  }
  if (maxValue <= 0) return null

  const threshold = Math.max(0.05, maxValue * 0.15)
  const minRun = Math.max(2, Math.floor(samples.length * 0.005))

  let firstIndex = -1
  let lastIndex = -1
  let runStart = -1
  let runLength = 0

  for (let i = 0; i < samples.length; i += 1) {
    if (samples[i] >= threshold) {
      if (runStart < 0) runStart = i
      runLength += 1
      if (runLength >= minRun && firstIndex < 0) {
        firstIndex = runStart
      }
      if (runLength >= minRun) {
        lastIndex = i
      }
    } else {
      runStart = -1
      runLength = 0
    }
  }

  if (firstIndex < 0 || lastIndex < 0 || lastIndex <= firstIndex) return null

  const bucketMs = durationMs / samples.length
  const startMs = Math.max(0, firstIndex * bucketMs)
  const endMs = Math.min(durationMs, (lastIndex + 1) * bucketMs)

  if (endMs - startMs < 40) return null
  return { startMs, endMs }
}

function createWordTimeMapper(
  words: NarrationTranscription['words'],
  durationMs: number,
  speechBounds: SpeechBounds | null,
) {
  if (!words.length) {
    return {
      map: (ms: number) => Math.max(0, Math.min(durationMs, ms)),
      calibrated: false,
    }
  }

  let firstStartMs = Number.POSITIVE_INFINITY
  let lastEndMs = Number.NEGATIVE_INFINITY

  for (const word of words) {
    if (Number.isFinite(word.start)) {
      firstStartMs = Math.min(firstStartMs, word.start * 1000)
    }
    if (Number.isFinite(word.end)) {
      lastEndMs = Math.max(lastEndMs, word.end * 1000)
    }
  }

  if (!Number.isFinite(firstStartMs) || !Number.isFinite(lastEndMs)) {
    return {
      map: (ms: number) => Math.max(0, Math.min(durationMs, ms)),
      calibrated: false,
    }
  }

  firstStartMs = Math.max(0, firstStartMs)
  lastEndMs = Math.max(firstStartMs + 1, lastEndMs)

  let calibrated = false
  if (speechBounds) {
    const driftStart = Math.abs(firstStartMs - speechBounds.startMs)
    const driftEnd = Math.abs(lastEndMs - speechBounds.endMs)
    const spanDiff = Math.abs((lastEndMs - firstStartMs) - (speechBounds.endMs - speechBounds.startMs))

    calibrated = driftStart > 120 || driftEnd > 120 || spanDiff > 180
  }

  const clamp = (value: number) => Math.max(0, Math.min(durationMs, value))

  if (!calibrated || !speechBounds) {
    return {
      map: (ms: number) => clamp(ms),
      calibrated: false,
    }
  }

  const transcriptionSpan = Math.max(1, lastEndMs - firstStartMs)
  const speechSpan = Math.max(1, speechBounds.endMs - speechBounds.startMs)

  return {
    map: (ms: number) => {
      const ratio = (ms - firstStartMs) / transcriptionSpan
      return clamp(speechBounds.startMs + (ratio * speechSpan))
    },
    calibrated: true,
  }
}

function applyCanvasResolution(canvas: HTMLCanvasElement) {
  const ratio = window.devicePixelRatio || 1
  const rect = canvas.getBoundingClientRect()

  canvas.width = Math.max(1, Math.floor(rect.width * ratio))
  canvas.height = Math.max(1, Math.floor(rect.height * ratio))

  const context = canvas.getContext('2d')
  if (!context) return null

  context.setTransform(1, 0, 0, 1, 0, 0)
  context.scale(ratio, ratio)

  return { context, width: rect.width, height: rect.height }
}

async function decodeSegmentAudio(
  segmentId: number,
  expectedVersion: number,
  source: 'original' | 'cleaned' = 'original',
) {
  if (!import.meta.client) return null

  const context = getAudioContext()
  if (!context) return null

  const audioUrl = source === 'cleaned'
    ? `${baseURL}/api/segments/${segmentId}/audio/cleaned?v=${expectedVersion}`
    : `${baseURL}/api/segments/${segmentId}/audio?v=${expectedVersion}`
  const response = await fetch(audioUrl)
  if (!response.ok) {
    throw new Error(`Audio fetch failed (${response.status})`)
  }

  const bytes = await response.arrayBuffer()
  if ((audioVersion[segmentId] || 0) !== expectedVersion) return null
  return context.decodeAudioData(bytes.slice(0))
}

async function fetchSegmentWaveform(
  segmentId: number,
  points: number,
  source: 'original' | 'cleaned' = 'original',
) {
  return await $fetch<SegmentWaveformResponse>(`${baseURL}/api/segments/${segmentId}/waveform`, {
    query: {
      points,
      source,
    },
  })
}

async function loadVoiceDraftWaveform() {
  if (!import.meta.client || !voiceDraft.value) return

  const context = getAudioContext()
  if (!context) return

  const draftId = voiceDraft.value.id
  const expectedVersion = voiceDraftAudioVersion.value

  try {
    const response = await fetch(voiceSampleDraftAudioUrl(draftId))
    if (!response.ok) {
      throw new Error(`Draft audio fetch failed (${response.status})`)
    }

    const bytes = await response.arrayBuffer()
    if (!voiceDraft.value || voiceDraft.value.id !== draftId || voiceDraftAudioVersion.value !== expectedVersion) return

    const decoded = await context.decodeAudioData(bytes.slice(0))
    if (!voiceDraft.value || voiceDraft.value.id !== draftId || voiceDraftAudioVersion.value !== expectedVersion) return

    voiceDraftAudioDurationMs.value = Math.max(MIN_TRIM_GAP_MS, Math.round(decoded.duration * 1000))
    voiceDraftWaveformData.value = buildWaveformSamples(decoded.getChannelData(0), 520)
    clampVoiceDraftTrim()

    await nextTick()
    drawVoiceDraftWaveform()
  } catch (err) {
    console.error('Failed to load voice draft waveform', err)
  }
}

function drawVoiceDraftWaveform() {
  if (!import.meta.client || !voiceDraft.value) return

  const samples = voiceDraftWaveformData.value
  if (!samples) return

  const canvas = document.getElementById('voice-draft-waveform') as HTMLCanvasElement | null
  if (!canvas) return

  const frame = applyCanvasResolution(canvas)
  if (!frame) return

  const { context, width, height } = frame
  context.clearRect(0, 0, width, height)

  const totalMs = voiceDraftDurationMs.value
  if (!totalMs) return

  const gap = width / samples.length
  const barWidth = Math.max(1, gap - 0.5)
  const midY = height / 2
  const isDark = document.documentElement.classList.contains('dark')

  for (let i = 0; i < samples.length; i += 1) {
    const ms = (i / samples.length) * totalMs
    const inRange = ms >= voiceDraftTrimStartMs.value && ms <= voiceDraftTrimEndMs.value
    const barHeight = Math.max(1, samples[i] * (height * 0.78))

    context.fillStyle = inRange
      ? (isDark ? 'rgba(99,102,241,0.72)' : 'rgba(79,70,229,0.62)')
      : (isDark ? 'rgba(107,114,128,0.26)' : 'rgba(156,163,175,0.32)')

    context.fillRect(i * gap, midY - (barHeight / 2), barWidth, barHeight)
  }

  const words = voiceDraft.value.words || []
  if (!words.length) return

  const speechBounds = detectSpeechBounds(samples, totalMs)
  const mapper = createWordTimeMapper(words, totalMs, speechBounds)

  context.font = '9px ui-sans-serif, system-ui, -apple-system, Segoe UI'
  context.textAlign = 'left'

  for (const word of words) {
    const startMs = mapper.map(word.start * 1000)
    const endMs = mapper.map(word.end * 1000)
    const x = Math.max(0, Math.min(width - 1, (startMs / totalMs) * width))
    const inRange = startMs >= voiceDraftTrimStartMs.value && endMs <= voiceDraftTrimEndMs.value

    context.fillStyle = inRange
      ? (isDark ? 'rgba(168,85,247,0.78)' : 'rgba(147,51,234,0.6)')
      : (isDark ? 'rgba(107,114,128,0.38)' : 'rgba(148,163,184,0.42)')

    context.fillRect(x, height - 14, 1, 14)
  }
}

function onVoiceDraftTrimPointerDown(event: PointerEvent, handle: TrimHandle) {
  event.preventDefault()
  if (!voiceDraft.value) return

  voiceDraftDragging.value = handle
  const expectedDraftId = voiceDraft.value.id

  const onMove = (moveEvent: PointerEvent) => {
    if (!voiceDraft.value || voiceDraft.value.id !== expectedDraftId) return

    const canvas = document.getElementById('voice-draft-waveform') as HTMLCanvasElement | null
    if (!canvas) return

    const rect = canvas.getBoundingClientRect()
    const fraction = Math.max(0, Math.min(1, (moveEvent.clientX - rect.left) / rect.width))
    const nextMs = Math.round(fraction * voiceDraftDurationMs.value)

    if (voiceDraftDragging.value === 'start') {
      voiceDraftTrimStartMs.value = Math.min(nextMs, voiceDraftTrimEndMs.value - MIN_TRIM_GAP_MS)
    } else if (voiceDraftDragging.value === 'end') {
      voiceDraftTrimEndMs.value = Math.max(nextMs, voiceDraftTrimStartMs.value + MIN_TRIM_GAP_MS)
    }

    clampVoiceDraftTrim()
    drawVoiceDraftWaveform()
  }

  const onUp = () => {
    voiceDraftDragging.value = null
    document.removeEventListener('pointermove', onMove)
    document.removeEventListener('pointerup', onUp)
  }

  document.addEventListener('pointermove', onMove)
  document.addEventListener('pointerup', onUp)
}

function getActiveWordIdx(segmentId: number) {
  if (timelinePlayingIdx.value < 0) return -1
  const segment = segments.value[timelinePlayingIdx.value]
  if (!segment || segment.id !== segmentId) return -1

  const transcription = transcriptions[segmentId]
  if (!transcription?.words?.length) return -1

  const currentTime = timelineCurrentTime.value
  for (let index = transcription.words.length - 1; index >= 0; index -= 1) {
    const word = transcription.words[index]
    if (currentTime >= word.start && currentTime <= word.end) {
      return index
    }
  }

  return -1
}

async function loadWaveform(segmentId: number, options: WaveformLoadOptions = {}) {
  const segment = segments.value.find(item => item.id === segmentId)
  if (!segment || segment.status !== 'done') return
  if (!timelineSegmentHasAudio(segment)) return

  if (!options.force && waveformData[segmentId]) {
    drawWaveform(segmentId)
    return
  }

  if (waveformLoading[segmentId]) return
  waveformLoading[segmentId] = true

  const expectedVersion = audioVersion[segmentId] || 0

  try {
    const preferredSource: 'cleaned' | 'original' = segment.studio_voice_audio_path ? 'cleaned' : 'original'
    const fallbackSource: 'cleaned' | 'original' = preferredSource === 'cleaned' ? 'original' : 'cleaned'
    const hasFallbackAudio = fallbackSource === 'cleaned'
      ? !!segment.studio_voice_audio_path
      : !!segment.audio_path

    let decoded: AudioBuffer | null = null
    try {
      decoded = await decodeSegmentAudio(segmentId, expectedVersion, preferredSource)
    } catch (err) {
      console.error('Failed to decode browser waveform for segment', segmentId, err)
      if (hasFallbackAudio) {
        try {
          decoded = await decodeSegmentAudio(segmentId, expectedVersion, fallbackSource)
        } catch (fallbackErr) {
          console.error('Failed fallback decode for segment', segmentId, fallbackErr)
        }
      }
    }

    if (decoded && (audioVersion[segmentId] || 0) === expectedVersion) {
      const samples = buildWaveformSamples(decoded.getChannelData(0), 200)
      const durationMs = Math.max(1, Math.round(decoded.duration * 1000))
      waveformData[segmentId] = samples
      waveformMeta[segmentId] = {
        durationMs,
        speechBounds: detectSpeechBounds(samples, durationMs),
      }
      await nextTick()
      drawWaveform(segmentId)
      return
    }

    let serverWaveform: SegmentWaveformResponse | null = null
    try {
      serverWaveform = await fetchSegmentWaveform(segmentId, 200, preferredSource)
    } catch {
      if (hasFallbackAudio) {
        serverWaveform = await fetchSegmentWaveform(segmentId, 200, fallbackSource)
      }
    }

    if (!serverWaveform || (audioVersion[segmentId] || 0) !== expectedVersion) return
    const samples = Float32Array.from(serverWaveform.samples)
    const durationMs = Math.max(1, Math.round(serverWaveform.duration_ms))
    waveformData[segmentId] = samples
    waveformMeta[segmentId] = {
      durationMs,
      speechBounds: detectSpeechBounds(samples, durationMs),
    }
    await nextTick()
    drawWaveform(segmentId)
  } catch (err) {
    console.error('Failed to load waveform for segment', segmentId, err)
  } finally {
    delete waveformLoading[segmentId]
  }
}

function drawWaveform(segmentId: number) {
  if (!import.meta.client) return

  const canvas = document.getElementById(`waveform-${segmentId}`) as HTMLCanvasElement | null
  if (!canvas) return

  const samples = waveformData[segmentId]
  if (!samples) return

  const segment = segments.value.find(item => item.id === segmentId)
  const frame = applyCanvasResolution(canvas)
  if (!frame || !segment) return

  const { context, width, height } = frame
  context.clearRect(0, 0, width, height)

  const isDark = document.documentElement.classList.contains('dark')
  let barColor = isDark ? 'rgba(148,163,184,0.45)' : 'rgba(100,116,139,0.4)'

  if (segment.status === 'done') {
    barColor = isDark ? 'rgba(52,211,153,0.62)' : 'rgba(16,185,129,0.5)'
  } else if (segment.status === 'error') {
    barColor = isDark ? 'rgba(248,113,113,0.62)' : 'rgba(239,68,68,0.5)'
  } else if (segment.status === 'generating') {
    barColor = isDark ? 'rgba(251,191,36,0.6)' : 'rgba(245,158,11,0.5)'
  }

  const gap = width / samples.length
  const barWidth = Math.max(1, gap - 0.7)
  const midY = height / 2

  context.fillStyle = barColor
  for (let i = 0; i < samples.length; i += 1) {
    const barHeight = Math.max(1, samples[i] * (height * 0.82))
    context.fillRect(i * gap, midY - (barHeight / 2), barWidth, barHeight)
  }

  const transcription = transcriptions[segmentId]
  const words = transcription?.words || []
  const meta = waveformMeta[segmentId]
  const durationMs = meta?.durationMs || Math.max(1, Math.round((segment.duration_seconds || 0) * 1000))
  if (!durationMs || !words.length) return

  const mapper = createWordTimeMapper(words, durationMs, meta?.speechBounds || null)

  const activeWordIdx = getActiveWordIdx(segmentId)
  for (let index = 0; index < words.length; index += 1) {
    const word = words[index]
    const markerMs = mapper.map(word.start * 1000)
    const x = Math.max(0, Math.min(width - 1, (markerMs / durationMs) * width))
    const isActive = index === activeWordIdx

    context.fillStyle = isActive
      ? (isDark ? 'rgba(196,181,253,0.95)' : 'rgba(79,70,229,0.9)')
      : (isDark ? 'rgba(196,181,253,0.6)' : 'rgba(99,102,241,0.45)')
    context.fillRect(x, height - (isActive ? 16 : 12), isActive ? 2 : 1, isActive ? 16 : 12)
  }
}

function drawAllWaveforms() {
  for (const segment of segments.value) {
    drawWaveform(segment.id)
  }
}

function setupTimelineResizeObserver() {
  if (!import.meta.client) return

  const element = timelineScrollEl.value
  if (!element) return

  timelineContainerWidth.value = element.clientWidth

  if (timelineResizeObserver) {
    timelineResizeObserver.disconnect()
  }

  timelineResizeObserver = new ResizeObserver(entries => {
    for (const entry of entries) {
      timelineContainerWidth.value = entry.contentRect.width
    }
  })

  timelineResizeObserver.observe(element)
}

function teardownTimelineResizeObserver() {
  if (!timelineResizeObserver) return
  timelineResizeObserver.disconnect()
  timelineResizeObserver = null
}

async function openTimelinePanel() {
  await nextTick()
  setupTimelineResizeObserver()

  for (const segment of segments.value) {
    if (segment.status === 'done' && timelineSegmentHasAudio(segment)) {
      void loadWaveform(segment.id)
    }
  }

  drawAllWaveforms()
}

function onTimelineScroll() {
  const element = timelineScrollEl.value
  if (!element) return
  timelineScrollLeft.value = element.scrollLeft
}

function onMinimapClick(event: MouseEvent) {
  const scrollElement = timelineScrollEl.value
  if (!scrollElement) return

  const target = event.currentTarget as HTMLElement
  const rect = target.getBoundingClientRect()
  const clickFraction = Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width))
  const viewport = timelineViewportRatio.value
  const centeredFraction = Math.max(0, clickFraction - (viewport / 2))
  const maxScroll = Math.max(0, scrollElement.scrollWidth - scrollElement.clientWidth)

  scrollElement.scrollLeft = centeredFraction * maxScroll
}

function animateWordTrackScroll() {
  const track = wordTrackScrollEl.value
  if (!track) {
    wordTrackAnimating = false
    return
  }

  const diff = wordTrackScrollTarget - track.scrollLeft
  if (Math.abs(diff) < 1) {
    track.scrollLeft = wordTrackScrollTarget
    wordTrackAnimating = false
    return
  }

  track.scrollLeft += diff * 0.12
  wordTrackAnimating = true
  requestAnimationFrame(animateWordTrackScroll)
}

function scrollWordTrackToActive() {
  const track = wordTrackScrollEl.value
  if (!track || timelinePlayingIdx.value < 0) return

  const activeWord = track.querySelector('.word-active') as HTMLElement | null
  if (!activeWord) return

  const trackRect = track.getBoundingClientRect()
  const wordRect = activeWord.getBoundingClientRect()
  const wordCenter = wordRect.left + (wordRect.width / 2) - trackRect.left + track.scrollLeft

  wordTrackScrollTarget = Math.max(0, wordCenter - (track.clientWidth / 3))
  if (!wordTrackAnimating) {
    animateWordTrackScroll()
  }
}

function scrollTimelineToCursor() {
  const scrollElement = timelineScrollEl.value
  if (!scrollElement || timelinePlayingIdx.value < 0) return

  const cursorPixel = (timelineCursorPercent.value / 100) * scrollElement.scrollWidth
  const viewportLeft = scrollElement.scrollLeft
  const viewportRight = viewportLeft + scrollElement.clientWidth
  const margin = scrollElement.clientWidth * 0.25

  if (cursorPixel < viewportLeft + margin) {
    scrollElement.scrollLeft = Math.max(0, cursorPixel - margin)
  } else if (cursorPixel > viewportRight - margin) {
    scrollElement.scrollLeft = Math.min(
      scrollElement.scrollWidth - scrollElement.clientWidth,
      cursorPixel - scrollElement.clientWidth + margin,
    )
  }

  scrollWordTrackToActive()
}

function cancelTimelineAnimationLoop() {
  if (timelineAnimFrame === null) return
  cancelAnimationFrame(timelineAnimFrame)
  timelineAnimFrame = null
}

function startTimelineAnimationLoop() {
  cancelTimelineAnimationLoop()

  const tick = () => {
    if (!timelineIsPlaying.value) {
      timelineAnimFrame = null
      return
    }

    onTimelineTimeUpdate()
    timelineAnimFrame = requestAnimationFrame(tick)
  }

  timelineAnimFrame = requestAnimationFrame(tick)
}

function playTimelineSegment(startIndex: number) {
  if (!timelineAudioPlayer.value) return

  let index = startIndex
  while (index < segments.value.length) {
    const segment = segments.value[index]
    if (segment.status === 'done' && timelineSegmentHasAudio(segment)) {
      break
    }
    index += 1
  }

  if (index >= segments.value.length) {
    stopTimelinePlayback()
    return
  }

  timelinePlayingIdx.value = index
  timelineCurrentTime.value = 0

  const segment = segments.value[index]
  const player = timelineAudioPlayer.value
  const preferredSource: 'cleaned' | 'original' = segment.studio_voice_audio_path ? 'cleaned' : 'original'
  const hasOriginalFallback = preferredSource === 'cleaned' && !!segment.audio_path

  player.src = timelineAudioUrl(segment, preferredSource)
  player.playbackRate = playbackSpeed.value
  player.play().catch(() => {
    if (hasOriginalFallback) {
      player.src = timelineAudioUrl(segment, 'original')
      player.playbackRate = playbackSpeed.value
      player.play().catch(() => {
        timelineIsPlaying.value = false
        cancelTimelineAnimationLoop()
      })
      return
    }
    timelineIsPlaying.value = false
    cancelTimelineAnimationLoop()
  })

  drawWaveform(segment.id)
}

function startTimelinePlayback(startIndex: number) {
  if (!timelineHasDoneSegments.value) return

  timelineIsPlaying.value = true
  playTimelineSegment(startIndex)
  startTimelineAnimationLoop()
}

function stopTimelinePlayback() {
  const player = timelineAudioPlayer.value
  if (player) {
    player.pause()
    player.removeAttribute('src')
    player.load()
  }

  timelinePlayingIdx.value = -1
  timelineCurrentTime.value = 0
  timelineIsPlaying.value = false
  cancelTimelineAnimationLoop()
  drawAllWaveforms()
}

function toggleTimelinePlayPause() {
  if (timelineIsPlaying.value) {
    const player = timelineAudioPlayer.value
    if (player) {
      player.pause()
    }
    timelineIsPlaying.value = false
    cancelTimelineAnimationLoop()
    return
  }

  if (timelinePlayingIdx.value >= 0) {
    const player = timelineAudioPlayer.value
    if (player) {
      player.playbackRate = playbackSpeed.value
      player.play().catch(() => {})
    }
    timelineIsPlaying.value = true
    startTimelineAnimationLoop()
    return
  }

  startTimelinePlayback(0)
}

function timelineClickSegment(index: number) {
  startTimelinePlayback(index)
}

function onTimelineAudioEnded() {
  if (timelinePlayingIdx.value < 0) return
  playTimelineSegment(timelinePlayingIdx.value + 1)
}

function onTimelineTimeUpdate() {
  const player = timelineAudioPlayer.value
  if (!player) return

  timelineCurrentTime.value = player.currentTime
  scrollTimelineToCursor()

  const currentSegment = segments.value[timelinePlayingIdx.value]
  if (currentSegment) {
    drawWaveform(currentSegment.id)
  }
}

async function fetchSegments() {
  const requestId = ++fetchSegmentsRequestId
  const projectId = props.projectId

  loading.value = true
  error.value = null

  try {
    const data = await $fetch<NarrationSegment[]>(`${baseURL}/api/projects/${projectId}/segments`)
    if (requestId !== fetchSegmentsRequestId || projectId !== props.projectId) return
    setSegments(data)
  } catch (err: any) {
    if (requestId !== fetchSegmentsRequestId || projectId !== props.projectId) return
    error.value = err?.data?.detail || err?.message || 'Failed to fetch narration segments'
  } finally {
    if (requestId === fetchSegmentsRequestId && projectId === props.projectId) {
      loading.value = false
    }
  }
}

async function fetchVariants(segmentId: number) {
  const data = await $fetch<NarrationVariant[]>(`${baseURL}/api/segments/${segmentId}/variants`)
  variantsMap[segmentId] = data
}

async function fetchVoiceSamples() {
  const data = await $fetch<NarrationVoiceSample[]>(`${baseURL}/api/voice-samples`)
  voiceSamples.value = data

  const sampleIds = new Set(data.map(sample => sample.id))
  for (const key of Object.keys(voiceSampleTranscriptDrafts)) {
    const sampleId = Number(key)
    if (!sampleIds.has(sampleId)) {
      delete voiceSampleTranscriptDrafts[sampleId]
    }
  }
  for (const key of Object.keys(voiceSampleSaving)) {
    const sampleId = Number(key)
    if (!sampleIds.has(sampleId)) {
      delete voiceSampleSaving[sampleId]
    }
  }
  for (const sample of data) {
    voiceSampleTranscriptDrafts[sample.id] = sample.transcript || ''
    if (!voiceSampleSaving[sample.id]) {
      voiceSampleSaving[sample.id] = false
    }
  }

  if (!data.find(sample => sample.id === globalVoiceSampleId.value)) {
    globalVoiceSampleId.value = null
  }
}

async function fetchMagpieVoices() {
  try {
    const data = await $fetch<{ voices: string[] }>(`${baseURL}/api/voices`)
    magpieVoices.value = data.voices || []
  } catch (err: any) {
    status.value = err?.data?.detail || 'Failed to load Magpie voices'
  }
}

async function fetchProjectTranscriptions() {
  const projectId = props.projectId

  try {
    const data = await $fetch<Record<string, NarrationTranscription>>(
      `${baseURL}/api/projects/${projectId}/transcriptions`,
    )

    if (projectId !== props.projectId) return

    for (const key of Object.keys(transcriptions)) {
      delete transcriptions[Number(key)]
    }

    const validIds = new Set(segments.value.map(segment => segment.id))
    for (const [segmentId, transcription] of Object.entries(data)) {
      const id = Number(segmentId)
      if (validIds.has(id)) {
        transcriptions[id] = transcription
      }
    }

    if (showTimeline.value) {
      nextTick(() => drawAllWaveforms())
    }
  } catch {
    // Optional data. Keep UI interactive if unavailable.
  }
}

async function addSegment() {
  if (!addText.value.trim()) return

  try {
    await $fetch(`${baseURL}/api/projects/${props.projectId}/segments`, {
      method: 'POST',
      body: {
        text: addText.value.trim(),
        service: addService.value,
        magpie_voice: addService.value === 'magpie' ? (globalMagpieVoice.value || null) : null,
      },
    })
    addText.value = ''
    showAdd.value = false
    await fetchSegments()
  } catch (err: any) {
    status.value = err?.data?.detail || 'Failed to add segment'
  }
}

function startInsert(position: number) {
  insertAtPosition.value = position
  insertText.value = ''
  insertService.value = addService.value
}

function cancelInsert() {
  insertAtPosition.value = null
  insertText.value = ''
}

async function insertSegment() {
  if (insertAtPosition.value === null || !insertText.value.trim()) return

  try {
    await $fetch(`${baseURL}/api/projects/${props.projectId}/segments`, {
      method: 'POST',
      body: {
        text: insertText.value.trim(),
        position: insertAtPosition.value,
        service: insertService.value,
        voice_sample_id: insertService.value === 'dia' ? (globalVoiceSampleId.value || null) : null,
        magpie_voice: insertService.value === 'magpie' ? (globalMagpieVoice.value || null) : null,
      },
    })

    insertText.value = ''
    insertAtPosition.value = null
    await fetchSegments()
  } catch (err: any) {
    status.value = err?.data?.detail || 'Failed to insert segment'
  }
}

function startEdit(segment: NarrationSegment) {
  editingId.value = segment.id
  editText.value = segment.text
}

async function saveEdit(segmentId: number) {
  if (!editText.value.trim()) return

  try {
    const updated = await $fetch<NarrationSegment>(`${baseURL}/api/segments/${segmentId}`, {
      method: 'PUT',
      body: { text: editText.value.trim() },
    })

    updateSegmentInPlace(updated)
    delete transcriptions[segmentId]

    editingId.value = null
    editText.value = ''
  } catch (err: any) {
    status.value = err?.data?.detail || 'Failed to save segment'
  }
}

async function refreshSplitPreview(segmentId: number) {
  const targetWords = normalizedSplitTargetWords()
  splitPreviewLoading.value = true

  try {
    const preview = await $fetch<NarrationSegmentSplitPreview>(`${baseURL}/api/segments/${segmentId}/split/preview`, {
      method: 'POST',
      body: { target_words: targetWords },
    })
    if (splitSegmentId.value === segmentId) {
      splitPreview.value = preview
    }
  } catch (err: any) {
    if (splitSegmentId.value === segmentId) {
      splitPreview.value = null
    }
    status.value = err?.data?.detail || 'Failed to preview split'
  } finally {
    splitPreviewLoading.value = false
  }
}

async function openSplitPreview(segmentId: number) {
  if (splitSegmentId.value === segmentId) {
    resetSplitState({ keepTarget: true })
    return
  }

  splitSegmentId.value = segmentId
  splitPreview.value = null
  await refreshSplitPreview(segmentId)
}

async function applySegmentSplit(segmentId: number) {
  if (splitApplying.value || splitPreviewLoading.value) return
  if (splitSegmentId.value !== segmentId || !splitPreview.value?.can_split) return

  splitApplying.value = true
  const targetWords = normalizedSplitTargetWords()

  try {
    const payload = await $fetch<NarrationSegmentSplitResult>(`${baseURL}/api/segments/${segmentId}/split`, {
      method: 'POST',
      body: { target_words: targetWords },
    })

    setSegments(payload.segments)
    await fetchProjectTranscriptions()

    status.value = `Segment split into ${payload.created_count} segments`
    resetSplitState({ keepTarget: true })
  } catch (err: any) {
    status.value = err?.data?.detail || 'Failed to split segment'
  } finally {
    splitApplying.value = false
  }
}

async function onSegmentServiceChange(segment: NarrationSegment, event: Event) {
  const target = event.target as HTMLSelectElement
  const service = target.value as NarrationService

  try {
    const updated = await $fetch<NarrationSegment>(`${baseURL}/api/segments/${segment.id}`, {
      method: 'PUT',
      body: {
        service,
        magpie_voice: service === 'magpie' ? (globalMagpieVoice.value || null) : null,
      },
    })
    updateSegmentInPlace(updated)
  } catch (err: any) {
    status.value = err?.data?.detail || 'Failed to update service'
  }
}

async function moveSegment(segmentId: number, direction: -1 | 1) {
  const ordered = sortSegments(segments.value)
  const index = ordered.findIndex(segment => segment.id === segmentId)
  const target = index + direction
  if (index < 0 || target < 0 || target >= ordered.length) return

  const swapped = [...ordered]
  ;[swapped[index], swapped[target]] = [swapped[target], swapped[index]]

  const ordering = swapped.map((segment, idx) => ({ id: segment.id, position: idx + 1 }))

  try {
    const updated = await $fetch<NarrationSegment[]>(`${baseURL}/api/segments/reorder`, {
      method: 'POST',
      body: { ordering },
    })
    setSegments(updated)
  } catch (err: any) {
    status.value = err?.data?.detail || 'Failed to reorder segments'
  }
}

async function deleteSegment(segmentId: number) {
  if (!confirm('Delete this segment?')) return

  try {
    await $fetch(`${baseURL}/api/segments/${segmentId}`, { method: 'DELETE' })

    delete transcriptions[segmentId]
    delete variantsMap[segmentId]
    delete transcribing[segmentId]
    clearWaveform(segmentId)

    if (expandedTrim.value === segmentId) {
      expandedTrim.value = null
      resetTrimWaveformState()
    }

    await fetchSegments()
  } catch (err: any) {
    status.value = err?.data?.detail || 'Failed to delete segment'
  }
}

async function clearAllSegments() {
  if (!confirmClear.value) {
    confirmClear.value = true
    setTimeout(() => {
      confirmClear.value = false
    }, 2500)
    return
  }

  confirmClear.value = false

  try {
    await $fetch(`${baseURL}/api/projects/${props.projectId}/segments`, { method: 'DELETE' })

    for (const key of Object.keys(transcriptions)) {
      delete transcriptions[Number(key)]
    }
    for (const key of Object.keys(variantsMap)) {
      delete variantsMap[Number(key)]
    }
    for (const key of Object.keys(waveformData)) {
      delete waveformData[Number(key)]
    }
    for (const key of Object.keys(waveformLoading)) {
      delete waveformLoading[Number(key)]
    }
    for (const key of Object.keys(waveformMeta)) {
      delete waveformMeta[Number(key)]
    }

    expandedTrim.value = null
    resetTrimWaveformState()

    await fetchSegments()
  } catch (err: any) {
    status.value = err?.data?.detail || 'Failed to clear segments'
  }
}

async function doImportScript() {
  if (!importText.value.trim()) return

  try {
    await $fetch(`${baseURL}/api/projects/${props.projectId}/segments/import`, {
      method: 'POST',
      body: {
        text: importText.value,
        service: importService.value,
        magpie_voice: importService.value === 'magpie' ? (globalMagpieVoice.value || null) : null,
      },
    })

    importText.value = ''
    showImport.value = false

    await fetchSegments()
    await fetchProjectTranscriptions()
  } catch (err: any) {
    status.value = err?.data?.detail || 'Script import failed'
  }
}

async function processArticle() {
  if (!articleText.value.trim() || articleProcessing.value) return

  articleProcessing.value = true
  articleChunks.value = []
  articleStatus.value = 'Preparing article chunks...'

  try {
    const response = await fetch(`${baseURL}/api/projects/${props.projectId}/import-article`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        text: articleText.value,
        service: importService.value,
        magpie_voice: importService.value === 'magpie' ? (globalMagpieVoice.value || null) : null,
      }),
    })

    if (!response.ok || !response.body) {
      const detail = await response.text()
      throw new Error(detail || `HTTP ${response.status}`)
    }

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const blocks = buffer.split('\n\n')
      buffer = blocks.pop() || ''

      for (const block of blocks) {
        const line = block.trim()
        if (!line.startsWith('data: ')) continue

        const payload = JSON.parse(line.slice(6))

        if (payload.phase === 'splitting') {
          articleChunks.value = (payload.chunks || []).map((raw: string) => ({
            raw,
            segments: [raw],
            processed: false,
            error: false,
            retrying: false,
          }))
          articleStatus.value = `Processing ${(payload.chunks || []).length} chunks...`
        } else if (payload.phase === 'chunk_done') {
          const chunk = articleChunks.value[payload.index]
          if (chunk) {
            chunk.segments = payload.segments?.length ? payload.segments : [chunk.raw]
            chunk.processed = true
            chunk.error = false
          }
          articleStatus.value = `Processed ${payload.completed}/${payload.total} chunks`
        } else if (payload.phase === 'chunk_error') {
          const chunk = articleChunks.value[payload.index]
          if (chunk) {
            chunk.error = true
            chunk.processed = true
          }
          articleStatus.value = `Processed ${payload.completed}/${payload.total} chunks`
        } else if (payload.phase === 'processing') {
          articleStatus.value = payload.detail || articleStatus.value
        } else if (payload.phase === 'done') {
          articleStatus.value = payload.detail || 'Article processing complete'
        } else if (payload.phase === 'error') {
          throw new Error(payload.detail || 'Article processing failed')
        }
      }
    }
  } catch (err: any) {
    status.value = err?.message || 'Failed to process article'
  } finally {
    articleProcessing.value = false
  }
}

async function retryChunk(index: number) {
  const chunk = articleChunks.value[index]
  if (!chunk || chunk.retrying) return

  chunk.retrying = true
  chunk.error = false

  try {
    const response = await $fetch<{ segments: string[] }>(`${baseURL}/api/process-chunk`, {
      method: 'POST',
      body: { text: chunk.raw },
    })

    chunk.segments = response.segments.length ? response.segments : [chunk.raw]
    chunk.processed = true
    chunk.error = false
  } catch (err: any) {
    chunk.error = true
    chunk.processed = true
    status.value = err?.data?.detail || err?.message || 'Chunk retry failed'
  } finally {
    chunk.retrying = false
  }
}

async function retryAllFailedChunks() {
  const failures = articleChunks.value
    .map((chunk, index) => (chunk.error ? index : -1))
    .filter(index => index >= 0)

  for (const index of failures) {
    await retryChunk(index)
  }
}

function removeArticleSegment(chunkIndex: number, segmentIndex: number) {
  const chunk = articleChunks.value[chunkIndex]
  if (!chunk || chunk.segments.length <= 1) return
  chunk.segments.splice(segmentIndex, 1)
}

async function acceptArticleSegments() {
  const segmentsToImport: string[] = []
  const originals: string[] = []

  for (const chunk of articleChunks.value) {
    for (const item of chunk.segments) {
      const clean = item.trim()
      if (!clean) continue
      segmentsToImport.push(clean)
      originals.push(chunk.raw)
    }
  }

  if (!segmentsToImport.length) return

  try {
    await $fetch(`${baseURL}/api/projects/${props.projectId}/segments/import`, {
      method: 'POST',
      body: {
        text: segmentsToImport.join('\n'),
        service: importService.value,
        magpie_voice: importService.value === 'magpie' ? (globalMagpieVoice.value || null) : null,
        original_texts: originals,
      },
    })

    showImport.value = false
    articleText.value = ''
    articleChunks.value = []

    await fetchSegments()
    await fetchProjectTranscriptions()
  } catch (err: any) {
    status.value = err?.data?.detail || 'Failed to import article segments'
  }
}

function openScriptEditor() {
  scriptText.value = segments.value.map(segment => segment.text).join('\n')
  scriptSyncStatus.value = ''
  showScriptEditor.value = true
}

async function saveScript() {
  const lines = scriptText.value
    .split('\n')
    .map(line => line.trim())
    .filter(Boolean)

  if (!lines.length) return

  scriptSyncing.value = true
  scriptSyncStatus.value = ''

  try {
    const data = await $fetch<{
      segments: NarrationSegment[]
      changed: number
      added: number
      removed: number
    }>(`${baseURL}/api/projects/${props.projectId}/segments/sync`, {
      method: 'POST',
      body: { lines },
    })

    const parts = []
    if (data.changed) parts.push(`${data.changed} changed`)
    if (data.added) parts.push(`${data.added} added`)
    if (data.removed) parts.push(`${data.removed} removed`)

    scriptSyncStatus.value = parts.length ? parts.join(', ') : 'No changes'
    setSegments(data.segments)

    await fetchProjectTranscriptions()
  } catch (err: any) {
    scriptSyncStatus.value = err?.data?.detail || 'Script sync failed'
  } finally {
    scriptSyncing.value = false
  }
}

async function patchGlobalVoice(segmentIds: number[]) {
  for (const segmentId of segmentIds) {
    const segment = segments.value.find(item => item.id === segmentId)
    if (!segment) continue

    const payload: Record<string, any> = {}

    if (segment.service === 'dia' && globalVoiceSampleId.value !== null) {
      payload.voice_sample_id = globalVoiceSampleId.value || 0
    }

    if (segment.service === 'magpie' && globalMagpieVoice.value) {
      payload.magpie_voice = globalMagpieVoice.value
    }

    if (!Object.keys(payload).length) continue

    await $fetch(`${baseURL}/api/segments/${segmentId}`, {
      method: 'PUT',
      body: payload,
    })
  }
}

async function generateOne(segmentId: number) {
  try {
    await patchGlobalVoice([segmentId])
    await $fetch(`${baseURL}/api/segments/${segmentId}/generate`, { method: 'POST' })
    queuedSegmentIds.add(segmentId)
  } catch (err: any) {
    status.value = err?.data?.detail || 'Generation request failed'
  }
}

async function regenerate(segmentId: number) {
  try {
    await patchGlobalVoice([segmentId])
    const text = regenText[segmentId]?.trim()
    await $fetch(`${baseURL}/api/segments/${segmentId}/regenerate`, {
      method: 'POST',
      body: text ? { text } : {},
    })
    queuedSegmentIds.add(segmentId)
    regenText[segmentId] = ''
  } catch (err: any) {
    status.value = err?.data?.detail || 'Regeneration request failed'
  }
}

async function updateSegmentFlags(segmentId: number, flags: { is_final?: boolean; needs_review?: boolean }) {
  const updated = await $fetch<NarrationSegment>(`${baseURL}/api/segments/${segmentId}/flags`, {
    method: 'PATCH',
    body: flags,
  })
  updateSegmentInPlace(updated)
}

async function toggleFinal(segment: NarrationSegment) {
  try {
    await updateSegmentFlags(segment.id, { is_final: !segment.is_final })
  } catch (err: any) {
    status.value = err?.data?.detail || 'Failed to update final flag'
  }
}

async function clearNeedsReview(segment: NarrationSegment) {
  if (!segment.needs_review) return
  try {
    await updateSegmentFlags(segment.id, { needs_review: false })
  } catch (err: any) {
    status.value = err?.data?.detail || 'Failed to update needs review flag'
  }
}

async function markSegmentDone(segment: NarrationSegment) {
  try {
    const updated = await $fetch<NarrationSegment>(`${baseURL}/api/segments/${segment.id}/mark-done`, {
      method: 'POST',
    })
    updateSegmentInPlace(updated)
    status.value = `Segment ${segment.position} marked done`
  } catch (err: any) {
    status.value = err?.data?.detail || 'Failed to mark segment done'
  }
}

async function generateAll() {
  const pending = segments.value.filter(segment => segment.status !== 'done').map(segment => segment.id)
  if (!pending.length) return

  try {
    await patchGlobalVoice(pending)
    await $fetch(`${baseURL}/api/projects/${props.projectId}/generate/all`, { method: 'POST' })
    for (const segmentId of pending) {
      queuedSegmentIds.add(segmentId)
    }
  } catch (err: any) {
    status.value = err?.data?.detail || 'Generate-all request failed'
  }
}

async function cleanAllWithStudioVoice() {
  if (studioVoiceCleaningAll.value) return

  studioVoiceCleaningAll.value = true
  try {
    const response = await $fetch<{ message?: string; queued: number }>(
      `${baseURL}/api/projects/${props.projectId}/studio-voice/clean-all`,
      { method: 'POST' },
    )

    if (response.queued > 0) {
      status.value = `Queued Studio Voice cleaning for ${response.queued} audio item${response.queued === 1 ? '' : 's'}`
      setTimeout(() => {
        void fetchSegments()
      }, 1800)
    } else {
      status.value = response.message || 'All eligible audio is already Studio Voice cleaned'
      await fetchSegments()
    }
  } catch (err: any) {
    status.value = err?.data?.detail || 'Studio Voice clean-all request failed'
  } finally {
    studioVoiceCleaningAll.value = false
  }
}

async function retryFailed() {
  const failures = segments.value.filter(segment => segment.status === 'error').map(segment => segment.id)
  if (!failures.length) return

  try {
    await patchGlobalVoice(failures)
    await $fetch(`${baseURL}/api/projects/${props.projectId}/generate/failed`, { method: 'POST' })
    for (const segmentId of failures) {
      queuedSegmentIds.add(segmentId)
    }
  } catch (err: any) {
    status.value = err?.data?.detail || 'Retry request failed'
  }
}

async function cancelGeneration() {
  cancelling.value = true

  try {
    await $fetch(`${baseURL}/api/generation/cancel`, { method: 'POST' })
    ws?.send(JSON.stringify({ type: 'cancel' }))
  } finally {
    setTimeout(() => {
      cancelling.value = false
    }, 400)
  }
}

async function toggleVariants(segmentId: number) {
  if (expandedVariants.value === segmentId) {
    expandedVariants.value = null
    return
  }

  expandedVariants.value = segmentId
  await fetchVariants(segmentId)
}

async function selectVariant(segmentId: number, variantId: number) {
  try {
    const updated = await $fetch<NarrationSegment>(
      `${baseURL}/api/segments/${segmentId}/variants/${variantId}/select`,
      { method: 'POST' },
    )

    updateSegmentInPlace(updated)
    await fetchVariants(segmentId)

    if (showTimeline.value) {
      await loadWaveform(segmentId, { force: true })
    }

    void transcribeSegment(segmentId, { silent: true })
  } catch (err: any) {
    status.value = err?.data?.detail || 'Failed to select variant'
  }
}

async function deleteVariant(variant: NarrationVariant) {
  if (!confirm('Delete this variant?')) return

  try {
    await $fetch(`${baseURL}/api/variants/${variant.id}`, { method: 'DELETE' })

    await fetchVariants(variant.segment_id)
    await fetchSegments()

    if (showTimeline.value) {
      await loadWaveform(variant.segment_id, { force: true })
    }
  } catch (err: any) {
    status.value = err?.data?.detail || 'Failed to delete variant'
  }
}

async function deleteVoiceSample(sampleId: number) {
  if (!confirm('Delete this voice sample?')) return

  try {
    await $fetch(`${baseURL}/api/voice-samples/${sampleId}`, { method: 'DELETE' })

    if (globalVoiceSampleId.value === sampleId) {
      globalVoiceSampleId.value = null
    }

    await fetchVoiceSamples()
  } catch (err: any) {
    status.value = err?.data?.detail || 'Failed to delete voice sample'
  }
}

async function saveVoiceSampleTranscript(sampleId: number) {
  if (voiceSampleSaving[sampleId]) return

  const sample = voiceSamples.value.find(item => item.id === sampleId)
  if (!sample) return

  const transcript = voiceSampleTranscriptDrafts[sampleId] ?? ''
  if (transcript === sample.transcript) return

  voiceSampleSaving[sampleId] = true

  try {
    const updated = await $fetch<NarrationVoiceSample>(`${baseURL}/api/voice-samples/${sampleId}`, {
      method: 'PATCH',
      body: { transcript },
    })

    const index = voiceSamples.value.findIndex(item => item.id === sampleId)
    if (index >= 0) {
      voiceSamples.value[index] = updated
    }
    voiceSampleTranscriptDrafts[sampleId] = updated.transcript || ''
    status.value = `Voice text updated: ${updated.name}`
  } catch (err: any) {
    status.value = err?.data?.detail || 'Failed to update voice text'
  } finally {
    voiceSampleSaving[sampleId] = false
  }
}

function resetVoiceDraftState() {
  voiceDraft.value = null
  voiceDraftTranscript.value = ''
  voiceDraftTrimStartMs.value = 0
  voiceDraftTrimEndMs.value = MIN_TRIM_GAP_MS
  voiceDraftAudioDurationMs.value = null
  voiceDraftWaveformData.value = null
  voiceDraftDragging.value = null
  voiceDraftAudioVersion.value += 1
}

function setVoiceDraft(draft: NarrationVoiceSampleDraft) {
  voiceDraft.value = draft
  voiceDraftTranscript.value = draft.transcription || ''
  voiceDraftTrimStartMs.value = 0
  voiceDraftTrimEndMs.value = Math.max(MIN_TRIM_GAP_MS, Math.round(draft.duration_seconds * 1000))
  voiceDraftAudioDurationMs.value = null
  voiceDraftWaveformData.value = null
  voiceDraftDragging.value = null
  voiceDraftAudioVersion.value += 1
  nextTick(() => {
    void loadVoiceDraftWaveform()
  })
}

function clampVoiceDraftTrim() {
  const durationMs = voiceDraftDurationMs.value
  const maxStart = Math.max(0, durationMs - MIN_TRIM_GAP_MS)
  voiceDraftTrimStartMs.value = Math.max(0, Math.min(voiceDraftTrimStartMs.value, maxStart))
  voiceDraftTrimEndMs.value = Math.max(
    voiceDraftTrimStartMs.value + MIN_TRIM_GAP_MS,
    Math.min(voiceDraftTrimEndMs.value, durationMs),
  )
}

function onVoiceClipChange(event: Event) {
  const target = event.target as HTMLInputElement
  voiceClipFile.value = target.files?.[0] || null
}

async function uploadVoiceClip() {
  if (!voiceClipFile.value) return

  voiceDraftBusy.value = true

  try {
    if (voiceDraft.value) {
      const existingDraftId = voiceDraft.value.id
      await $fetch(`${baseURL}/api/voice-samples/drafts/${existingDraftId}`, { method: 'DELETE' }).catch(() => {})
      resetVoiceDraftState()
    }

    const formData = new FormData()
    formData.append('clip', voiceClipFile.value)

    const draft = await $fetch<NarrationVoiceSampleDraft>(`${baseURL}/api/voice-samples/drafts`, {
      method: 'POST',
      body: formData,
    })

    setVoiceDraft(draft)
    status.value = 'Clip uploaded and transcribed'
  } catch (err: any) {
    status.value = err?.data?.detail || 'Failed to process voice clip'
  } finally {
    voiceClipFile.value = null
    if (voiceClipInput.value) {
      voiceClipInput.value.value = ''
    }
    voiceDraftBusy.value = false
  }
}

function autoSuggestVoiceDraftTrim() {
  const draft = voiceDraft.value
  if (!draft?.words?.length) return

  const firstStart = draft.words[0].start * 1000
  const lastEnd = draft.words[draft.words.length - 1].end * 1000

  voiceDraftTrimStartMs.value = Math.max(0, Math.round(firstStart - 50))
  voiceDraftTrimEndMs.value = Math.min(voiceDraftDurationMs.value, Math.round(lastEnd + 50))
  clampVoiceDraftTrim()
  drawVoiceDraftWaveform()
}

async function applyVoiceDraftTrim() {
  if (!voiceDraft.value) return

  clampVoiceDraftTrim()
  if (voiceDraftTrimEndMs.value - voiceDraftTrimStartMs.value < MIN_TRIM_GAP_MS) {
    status.value = 'Trim range is too short'
    return
  }

  voiceDraftBusy.value = true

  try {
    const draft = await $fetch<NarrationVoiceSampleDraft>(`${baseURL}/api/voice-samples/drafts/${voiceDraft.value.id}/trim`, {
      method: 'POST',
      body: {
        start_ms: voiceDraftTrimStartMs.value,
        end_ms: voiceDraftTrimEndMs.value,
      },
    })

    setVoiceDraft(draft)
    status.value = 'Clip trimmed and transcription refreshed'
  } catch (err: any) {
    status.value = err?.data?.detail || 'Failed to trim voice clip'
  } finally {
    voiceDraftBusy.value = false
  }
}

async function retranscribeVoiceDraft() {
  if (!voiceDraft.value) return

  voiceDraftBusy.value = true

  try {
    const draft = await $fetch<NarrationVoiceSampleDraft>(`${baseURL}/api/voice-samples/drafts/${voiceDraft.value.id}/transcribe`, {
      method: 'POST',
    })
    setVoiceDraft(draft)
    status.value = 'Transcription updated'
  } catch (err: any) {
    status.value = err?.data?.detail || 'Failed to transcribe clip'
  } finally {
    voiceDraftBusy.value = false
  }
}

async function finalizeVoiceDraft() {
  if (!voiceDraft.value || !voiceName.value.trim()) return

  voiceDraftBusy.value = true

  try {
    const sample = await $fetch<NarrationVoiceSample>(`${baseURL}/api/voice-samples/drafts/${voiceDraft.value.id}/finalize`, {
      method: 'POST',
      body: {
        name: voiceName.value.trim(),
        transcript: voiceDraftTranscript.value.trim(),
      },
    })

    await fetchVoiceSamples()
    globalVoiceSampleId.value = sample.id
    status.value = 'Voice sample saved'
    voiceName.value = ''
    resetVoiceDraftState()
  } catch (err: any) {
    status.value = err?.data?.detail || 'Failed to save voice sample'
  } finally {
    voiceDraftBusy.value = false
  }
}

async function discardVoiceDraft(options: { silent?: boolean; skipConfirm?: boolean } = {}) {
  if (!voiceDraft.value) return
  if (!options.skipConfirm && !confirm('Discard this voice sample draft?')) return

  voiceDraftBusy.value = true
  const draftId = voiceDraft.value.id

  try {
    await $fetch(`${baseURL}/api/voice-samples/drafts/${draftId}`, { method: 'DELETE' })
    resetVoiceDraftState()
    if (!options.silent) {
      status.value = 'Voice draft discarded'
    }
  } catch (err: any) {
    if (!options.silent) {
      status.value = err?.data?.detail || 'Failed to discard draft'
    }
  } finally {
    voiceDraftBusy.value = false
  }
}

function exportAudio() {
  const params = new URLSearchParams({
    format: exportFormat.value,
    gap_ms: String(exportGapMs.value),
    fade_ms: String(exportFadeMs.value),
    normalize: String(exportNormalize.value),
  })

  if (import.meta.client) {
    window.location.href = `${baseURL}/api/projects/${props.projectId}/export?${params.toString()}`
  }
}

function exportAudioZip() {
  if (import.meta.client) {
    window.location.href = `${baseURL}/api/projects/${props.projectId}/export-zip`
  }
}

async function transcribeSegment(segmentId: number, options: { silent?: boolean } = {}) {
  if (transcribing[segmentId]) return false

  transcribing[segmentId] = true

  try {
    const transcription = await $fetch<NarrationTranscription>(`${baseURL}/api/segments/${segmentId}/transcribe`, {
      method: 'POST',
    })

    transcriptions[segmentId] = transcription

    if (showTimeline.value) {
      drawWaveform(segmentId)
    }

    if (expandedTrim.value === segmentId) {
      drawTrimWaveform(segmentId)
    }

    return true
  } catch (err: any) {
    if (!options.silent) {
      status.value = err?.data?.detail || 'Transcription failed'
    }
    return false
  } finally {
    delete transcribing[segmentId]
  }
}

async function transcribeAll() {
  const candidates = segments.value.filter(segment => segment.status === 'done' && segment.audio_path)
  if (!candidates.length) return

  const queue = candidates.filter(segment => !transcriptions[segment.id])
  if (!queue.length) {
    status.value = 'All generated segments already transcribed'
    return
  }

  transcribeAllProgress.value = { done: 0, total: queue.length }

  let failed = 0

  for (const segment of queue) {
    status.value = `Transcribing segment ${segment.position} (${transcribeAllProgress.value.done + 1}/${queue.length})...`

    const ok = await transcribeSegment(segment.id, { silent: true })
    if (!ok) failed += 1

    if (transcribeAllProgress.value) {
      transcribeAllProgress.value.done += 1
    }
  }

  const completed = queue.length - failed
  status.value = `Transcribed ${completed} segment${completed === 1 ? '' : 's'}${failed ? ` (${failed} failed)` : ''}`
  transcribeAllProgress.value = null
}

function toggleTranscript(segmentId: number) {
  expandedTranscript.value = expandedTranscript.value === segmentId ? null : segmentId
}

async function deleteTranscription(segmentId: number) {
  try {
    await $fetch(`${baseURL}/api/segments/${segmentId}/transcription`, { method: 'DELETE' })
    delete transcriptions[segmentId]
  } catch (err: any) {
    status.value = err?.data?.detail || 'Failed to delete transcription'
  }
}

function seekToWord(segmentId: number, startSeconds: number) {
  const segmentIndex = segments.value.findIndex(segment => segment.id === segmentId)
  if (segmentIndex < 0) return

  if (timelinePlayingIdx.value !== segmentIndex) {
    startTimelinePlayback(segmentIndex)
  }

  const player = timelineAudioPlayer.value
  if (!player) return

  player.currentTime = startSeconds
  timelineCurrentTime.value = startSeconds

  if (!timelineIsPlaying.value) {
    timelineIsPlaying.value = true
    player.play().catch(() => {})
    startTimelineAnimationLoop()
  }
}

function segmentNeedsTrim(segment: NarrationSegment) {
  if (!segmentHasTrimmableAudio(segment)) return false

  const transcription = transcriptions[segment.id]
  if (!transcription?.words?.length || !segment.duration_seconds) return false

  const firstWordStart = transcription.words[0]?.start || 0
  const lastWordEnd = transcription.words[transcription.words.length - 1]?.end || 0

  return firstWordStart > 0.3 || (segment.duration_seconds - lastWordEnd) > 0.5
}

function toggleTrim(segmentId: number) {
  if (expandedTrim.value === segmentId) {
    cancelTrimDeadspace()
    return
  }

  expandedTrim.value = segmentId
  stopTrimPreview()
  resetTrimSelectionState()
  trimWaveformError.value = ''

  if (!transcriptions[segmentId]) {
    void transcribeSegment(segmentId, { silent: true })
  }
}

async function loadTrimWaveform(segmentId: number) {
  const segment = segments.value.find(item => item.id === segmentId)
  if (!segment || !segmentHasTrimmableAudio(segment)) return

  const requestId = ++trimWaveformRequestId
  trimWaveformLoading.value = true
  trimWaveformError.value = ''

  try {
    let decoded: AudioBuffer | null = null
    let lastError: unknown = null

    for (let attempt = 0; attempt < 3; attempt += 1) {
      if (requestId !== trimWaveformRequestId || expandedTrim.value !== segmentId) {
        return
      }

      const expectedVersion = audioVersion[segmentId] || 0
      try {
        decoded = await decodeSegmentAudio(segmentId, expectedVersion)
      } catch (err) {
        lastError = err
      }

      if (decoded) break
      await new Promise(resolve => setTimeout(resolve, 120))
    }

    if (requestId !== trimWaveformRequestId || expandedTrim.value !== segmentId) {
      return
    }

    if (!decoded) {
      try {
        const serverWaveform = await fetchSegmentWaveform(segmentId, 520, 'original')
        if (requestId !== trimWaveformRequestId || expandedTrim.value !== segmentId) {
          return
        }

        trimSegmentId.value = segmentId
        trimDecodedBuffer.value = null
        trimAudioDuration.value = Math.max(1, Math.round(serverWaveform.duration_ms))
        trimWaveformData.value = Float32Array.from(serverWaveform.samples)

        resetTrimSelectionState()
        await nextTick()
        drawTrimWaveform(segmentId)
        trimWaveformError.value = ''
        return
      } catch (serverErr) {
        trimWaveformData.value = null
        trimDecodedBuffer.value = null
        resetTrimSelectionState()
        trimWaveformError.value = 'Could not load waveform. Try again.'
        if (lastError) {
          console.error('Failed to load trim waveform', lastError)
        }
        console.error('Server waveform fallback failed', serverErr)
        return
      }
    }

    trimSegmentId.value = segmentId
    trimDecodedBuffer.value = decoded
    trimAudioDuration.value = Math.max(1, Math.round(decoded.duration * 1000))
    trimWaveformData.value = buildWaveformSamples(decoded.getChannelData(0), 520)

    resetTrimSelectionState()

    await nextTick()
    drawTrimWaveform(segmentId)
    trimWaveformError.value = ''
  } catch (err) {
    if (requestId !== trimWaveformRequestId) return
    trimWaveformData.value = null
    trimDecodedBuffer.value = null
    resetTrimSelectionState()
    trimWaveformError.value = 'Could not load waveform. Try again.'
    console.error('Failed to load trim waveform', err)
  } finally {
    if (requestId === trimWaveformRequestId) {
      trimWaveformLoading.value = false
    }
  }
}

async function regenerateTrimWaveform(segmentId: number) {
  const segment = segments.value.find(item => item.id === segmentId)
  if (!segment || !segmentHasTrimmableAudio(segment)) return

  const requestId = ++trimWaveformRequestId
  trimWaveformLoading.value = true
  trimWaveformError.value = ''

  try {
    const serverWaveform = await fetchSegmentWaveform(segmentId, 520, 'original')
    if (requestId !== trimWaveformRequestId || expandedTrim.value !== segmentId) return

    trimSegmentId.value = segmentId
    trimDecodedBuffer.value = null
    trimAudioDuration.value = Math.max(1, Math.round(serverWaveform.duration_ms))
    trimWaveformData.value = Float32Array.from(serverWaveform.samples)
    resetTrimSelectionState()

    await nextTick()
    drawTrimWaveform(segmentId)
    status.value = 'Waveform regenerated from source audio'
  } catch (err: any) {
    trimWaveformError.value = err?.data?.detail || 'Could not regenerate waveform'
  } finally {
    if (requestId === trimWaveformRequestId) {
      trimWaveformLoading.value = false
    }
  }
}

function drawTrimWaveform(segmentId: number, attempt = 0) {
  if (!import.meta.client) return
  if (trimSegmentId.value !== segmentId) return

  const samples = trimWaveformData.value
  if (!samples) return

  const canvas = document.getElementById(`trim-waveform-${segmentId}`) as HTMLCanvasElement | null
  if (!canvas) {
    if (attempt < 6) {
      requestAnimationFrame(() => drawTrimWaveform(segmentId, attempt + 1))
    }
    return
  }

  const rect = canvas.getBoundingClientRect()
  if (rect.width < 4 || rect.height < 4) {
    if (attempt < 6) {
      requestAnimationFrame(() => drawTrimWaveform(segmentId, attempt + 1))
    }
    return
  }

  const frame = applyCanvasResolution(canvas)
  if (!frame) return

  const { context, width, height } = frame
  context.clearRect(0, 0, width, height)

  const totalMs = trimAudioDuration.value
  if (!totalMs) return

  const gap = width / samples.length
  const barWidth = Math.max(1, gap - 0.5)
  const midY = height / 2
  const isDark = document.documentElement.classList.contains('dark')
  const removeStartMs = trimSelectionStart.value
  const removeEndMs = trimSelectionEnd.value
  const hasSelection = hasTrimSelection.value

  for (let i = 0; i < samples.length; i += 1) {
    const ms = (i / samples.length) * totalMs
    const inRemovedRange = hasSelection && ms >= removeStartMs && ms <= removeEndMs
    const barHeight = Math.max(1, samples[i] * (height * 0.78))

    context.fillStyle = inRemovedRange
      ? (isDark ? 'rgba(248,113,113,0.74)' : 'rgba(239,68,68,0.64)')
      : (isDark ? 'rgba(56,189,248,0.36)' : 'rgba(14,165,233,0.3)')

    context.fillRect(i * gap, midY - (barHeight / 2), barWidth, barHeight)
  }

  const transcription = transcriptions[segmentId]
  if (!transcription?.words?.length) return

  const speechBounds = detectSpeechBounds(samples, totalMs)
  const mapper = createWordTimeMapper(transcription.words, totalMs, speechBounds)

  context.font = '9px ui-sans-serif, system-ui, -apple-system, Segoe UI'
  context.textAlign = 'left'

  for (const word of transcription.words) {
    const startMs = mapper.map(word.start * 1000)
    const endMs = mapper.map(word.end * 1000)
    const x = Math.max(0, Math.min(width - 1, (startMs / totalMs) * width))
    const inRemovedRange = hasSelection && startMs >= removeStartMs && endMs <= removeEndMs

    context.fillStyle = inRemovedRange
      ? (isDark ? 'rgba(248,113,113,0.85)' : 'rgba(220,38,38,0.72)')
      : (isDark ? 'rgba(125,211,252,0.56)' : 'rgba(3,105,161,0.48)')

    context.fillRect(x, height - 14, 1, 14)

    // Keep text labels on the marker itself (overlap is intentional).
    context.fillStyle = inRemovedRange
      ? (isDark ? 'rgba(254,202,202,0.95)' : 'rgba(127,29,29,0.86)')
      : (isDark ? 'rgba(186,230,253,0.95)' : 'rgba(8,47,73,0.78)')
    context.fillText(word.word, Math.min(width - 2, x + 2), height - 3)
  }
}

function stopTrimPreview() {
  if (!trimPreviewSource) return
  try {
    trimPreviewSource.stop()
  } catch {
    // no-op
  }
  trimPreviewSource.disconnect()
  trimPreviewSource = null
}

function resetTrimSelectionState() {
  trimStart.value = 0
  trimEnd.value = 0
  trimSelectionArmed.value = false
  trimSelecting.value = false
  trimSelectionAnchorMs.value = 0
}

function resetTrimWaveformState() {
  trimWaveformRequestId += 1
  trimSegmentId.value = null
  trimWaveformData.value = null
  trimDecodedBuffer.value = null
  trimAudioDuration.value = 1
  trimWaveformLoading.value = false
  trimWaveformError.value = ''
  resetTrimSelectionState()
  stopTrimPreview()
}

function beginTrimSelection() {
  if (!trimWaveformData.value || trimWaveformLoading.value) return
  resetTrimSelectionState()
  trimSelectionArmed.value = true
}

function clearTrimSelection() {
  const segmentId = expandedTrim.value
  resetTrimSelectionState()
  if (segmentId !== null) {
    drawTrimWaveform(segmentId)
  }
}

function cancelTrimDeadspace() {
  if (expandedTrim.value === null) {
    resetTrimWaveformState()
    return
  }
  expandedTrim.value = null
}

function trimMsFromPointerX(clientX: number, rect: DOMRect) {
  if (rect.width <= 0) return 0
  const fraction = Math.max(0, Math.min(1, (clientX - rect.left) / rect.width))
  return Math.round(fraction * trimAudioDuration.value)
}

function onTrimWaveformPointerDown(event: PointerEvent, segmentId: number) {
  if (
    !trimSelectionArmed.value
    || trimWaveformLoading.value
    || !trimWaveformData.value
    || trimSegmentId.value !== segmentId
  ) {
    return
  }

  const canvas = document.getElementById(`trim-waveform-${segmentId}`) as HTMLCanvasElement | null
  if (!canvas) return

  event.preventDefault()

  const startRect = canvas.getBoundingClientRect()
  const anchorMs = trimMsFromPointerX(event.clientX, startRect)

  trimSelectionAnchorMs.value = anchorMs
  trimStart.value = anchorMs
  trimEnd.value = anchorMs
  trimSelecting.value = true
  drawTrimWaveform(segmentId)

  const onMove = (moveEvent: PointerEvent) => {
    if (!trimSelecting.value) return
    const rect = canvas.getBoundingClientRect()
    const nextMs = trimMsFromPointerX(moveEvent.clientX, rect)

    trimStart.value = Math.min(trimSelectionAnchorMs.value, nextMs)
    trimEnd.value = Math.max(trimSelectionAnchorMs.value, nextMs)
    drawTrimWaveform(segmentId)
  }

  const onUp = () => {
    trimSelecting.value = false
    trimSelectionArmed.value = false

    if (!hasTrimSelection.value) {
      trimStart.value = 0
      trimEnd.value = 0
      status.value = 'Selection is too short. Drag a wider deadspace section.'
    }

    drawTrimWaveform(segmentId)
    document.removeEventListener('pointermove', onMove)
    document.removeEventListener('pointerup', onUp)
  }

  document.addEventListener('pointermove', onMove)
  document.addEventListener('pointerup', onUp)
}

async function previewTrim() {
  const segmentId = expandedTrim.value
  if (!segmentId || trimSegmentId.value !== segmentId) return
  if (!hasTrimSelection.value) {
    status.value = 'Select deadspace to preview'
    return
  }

  const context = getAudioContext()
  const decoded = trimDecodedBuffer.value
  if (!context || !decoded) return

  if (context.state === 'suspended') {
    await context.resume()
  }

  const startFrame = Math.max(
    0,
    Math.min(
      decoded.length,
      Math.round((trimSelectionStart.value / 1000) * decoded.sampleRate),
    ),
  )
  const endFrame = Math.max(
    startFrame,
    Math.min(
      decoded.length,
      Math.round((trimSelectionEnd.value / 1000) * decoded.sampleRate),
    ),
  )
  const removedFrames = endFrame - startFrame
  const nextLength = decoded.length - removedFrames
  if (removedFrames <= 0 || nextLength < 1) {
    status.value = 'Selected deadspace is not valid for preview'
    return
  }

  const previewBuffer = context.createBuffer(
    decoded.numberOfChannels,
    nextLength,
    decoded.sampleRate,
  )
  for (let channel = 0; channel < decoded.numberOfChannels; channel += 1) {
    const sourceData = decoded.getChannelData(channel)
    const targetData = previewBuffer.getChannelData(channel)
    targetData.set(sourceData.subarray(0, startFrame), 0)
    targetData.set(sourceData.subarray(endFrame), startFrame)
  }

  stopTrimPreview()
  const source = context.createBufferSource()
  source.buffer = previewBuffer
  source.playbackRate.value = playbackSpeed.value
  source.connect(context.destination)
  source.start(0)

  trimPreviewSource = source
  source.onended = () => {
    if (trimPreviewSource === source) {
      trimPreviewSource = null
    }
  }
}

async function applyTrim() {
  const segmentId = expandedTrim.value
  if (!segmentId) return

  const segment = segments.value.find(item => item.id === segmentId)
  if (!segment) return

  if (!hasTrimSelection.value) {
    status.value = 'Select deadspace to remove'
    return
  }

  if (trimAudioDuration.value - trimSelectionDuration.value < MIN_TRIM_GAP_MS) {
    status.value = 'Selected deadspace is too large to remove'
    return
  }

  trimApplying.value = true

  try {
    const payload = await $fetch<TrimResponse>(`${baseURL}/api/segments/${segment.id}/trim`, {
      method: 'POST',
      body: {
        start_ms: trimSelectionStart.value,
        end_ms: trimSelectionEnd.value,
        mode: 'remove',
      },
    })

    updateSegmentInPlace(payload.segment)

    if (payload.transcription) {
      transcriptions[segment.id] = payload.transcription
    } else {
      delete transcriptions[segment.id]
    }

    await loadTrimWaveform(segment.id)

    if (showTimeline.value) {
      await loadWaveform(segment.id, { force: true })
      drawWaveform(segment.id)
    }

    if (expandedVariants.value === segment.id) {
      await fetchVariants(segment.id)
    }

    status.value = 'Deadspace removed and saved'
  } catch (err: any) {
    status.value = err?.data?.detail || err?.message || 'Trim failed'
  } finally {
    trimApplying.value = false
  }
}

function toggleTimeline() {
  showTimeline.value = !showTimeline.value
}

function onAnyAudioPlay(event: Event) {
  const target = event.target as HTMLAudioElement | null
  if (!target || target.tagName !== 'AUDIO') return
  target.playbackRate = playbackSpeed.value
}

function connectWs() {
  if (!wsUrl.value) return

  if (ws) {
    ws.close()
    ws = null
  }

  ws = new WebSocket(wsUrl.value)

  ws.onmessage = event => {
    let message: any
    try {
      message = JSON.parse(event.data)
    } catch {
      return
    }

    handleWsMessage(message)
  }

  ws.onclose = () => {
    ws = null
    if (wsReconnectTimer) clearTimeout(wsReconnectTimer)
    wsReconnectTimer = setTimeout(() => {
      connectWs()
    }, 2000)
  }

  ws.onerror = () => {
    ws?.close()
  }
}

function isRelevantSegment(segmentId: number) {
  return segments.value.some(segment => segment.id === segmentId)
}

function markQueuedSegments(segmentIds: number[]) {
  for (const segmentId of segmentIds) {
    if (!isRelevantSegment(segmentId)) continue
    const segment = segments.value.find(item => item.id === segmentId)
    if (!segment || segment.status === 'generating') continue
    queuedSegmentIds.add(segmentId)
  }
}

async function handleWsMessage(message: any) {
  if (message.type === 'queued') {
    const queuedIds: number[] = message.segment_ids || []
    if (!queuedIds.some(id => isRelevantSegment(id))) return

    markQueuedSegments(queuedIds)
    generating.value = true
    genTotal.value = queuedIds.length
    genIndex.value = 0
    status.value = `Queued ${queuedIds.length} segment${queuedIds.length === 1 ? '' : 's'}...`
    return
  }

  if (message.type === 'segment_start') {
    if (!isRelevantSegment(message.segment_id)) return

    queuedSegmentIds.delete(message.segment_id)
    generating.value = true
    genTotal.value = message.total || genTotal.value
    genIndex.value = message.index || 0
    genEstimate.value = message.estimate_seconds || null

    const index = segments.value.findIndex(segment => segment.id === message.segment_id)
    if (index !== -1) {
      segments.value[index] = { ...segments.value[index], status: 'generating' }
    }

    status.value = `Generating segment ${message.index + 1}/${message.total}`
    return
  }

  if (message.type === 'segment_done') {
    if (!isRelevantSegment(message.segment_id)) return

    queuedSegmentIds.delete(message.segment_id)
    genIndex.value = (message.index || 0) + 1

    if (message.segment) {
      updateSegmentInPlace(message.segment as NarrationSegment)
    }

    if (showTimeline.value) {
      await loadWaveform(message.segment_id, { force: true })
    }

    if (!transcriptions[message.segment_id]) {
      void transcribeSegment(message.segment_id, { silent: true })
    }

    status.value = `Segment ${message.index + 1}/${message.total} complete`
    return
  }

  if (message.type === 'segment_error') {
    if (!isRelevantSegment(message.segment_id)) return

    queuedSegmentIds.delete(message.segment_id)
    genIndex.value = (message.index || 0) + 1

    if (message.segment) {
      updateSegmentInPlace(message.segment as NarrationSegment)
    } else {
      const index = segments.value.findIndex(segment => segment.id === message.segment_id)
      if (index !== -1) {
        segments.value[index] = {
          ...segments.value[index],
          status: 'error',
          error_message: message.error || 'Generation failed',
        }
      }
    }

    status.value = `Segment ${message.index + 1}/${message.total} failed`
    return
  }

  if (message.type === 'job_done') {
    generating.value = false
    cancelling.value = false
    genEstimate.value = null

    await fetchSegments()
    await fetchProjectTranscriptions()

    if (message.failed) {
      status.value = `Generation complete with ${message.failed} failure${message.failed === 1 ? '' : 's'}`
    } else {
      status.value = 'Generation complete'
    }

    return
  }

  if (message.type === 'job_cancelled') {
    generating.value = false
    cancelling.value = false
    genEstimate.value = null
    status.value = 'Generation cancelled'

    await fetchSegments()
    await fetchProjectTranscriptions()
    return
  }

  if (message.type === 'queue_status' && !message.active_job_id && !message.queue_length) {
    generating.value = false
    cancelling.value = false
    queuedSegmentIds.clear()
  }
}

function resetWorkspaceState() {
  fetchSegmentsRequestId += 1

  stopTimelinePlayback()
  teardownTimelineResizeObserver()

  setSegments([])

  for (const key of Object.keys(variantsMap)) {
    delete variantsMap[Number(key)]
  }
  for (const key of Object.keys(transcriptions)) {
    delete transcriptions[Number(key)]
  }
  for (const key of Object.keys(transcribing)) {
    delete transcribing[Number(key)]
  }
  for (const key of Object.keys(waveformData)) {
    delete waveformData[Number(key)]
  }
  for (const key of Object.keys(waveformLoading)) {
    delete waveformLoading[Number(key)]
  }
  for (const key of Object.keys(waveformMeta)) {
    delete waveformMeta[Number(key)]
  }

  editingId.value = null
  editText.value = ''
  resetSplitState()

  expandedVariants.value = null
  expandedTranscript.value = null
  expandedTrim.value = null

  resetTrimWaveformState()

  transcribeAllProgress.value = null

  showTimeline.value = false
  insertAtPosition.value = null
  insertText.value = ''

  status.value = ''
  error.value = null
  queuedSegmentIds.clear()
  studioVoiceCleaningAll.value = false
  collapsedSegmentIds.clear()
  segmentStatusFilter.value = 'all'
  segmentSortMode.value = 'position'
  doneTrimSuggestedOnly.value = false
  showFinalSegments.value = true
  showNeedsReviewOnly.value = false
}

watch(
  () => props.projectId,
  async () => {
    resetWorkspaceState()

    await fetchSegments()
    await fetchProjectVoiceDefaults()
    await Promise.all([
      fetchVoiceSamples(),
      fetchProjectTranscriptions(),
    ])
  },
  { immediate: true },
)

watch(
  () => segmentStatusFilter.value,
  nextFilter => {
    if (nextFilter !== 'done') {
      doneTrimSuggestedOnly.value = false
    }
  },
)

watch(
  () => globalVoiceSampleId.value,
  (nextValue, previousValue) => {
    if (applyingProjectVoiceDefaults.value || nextValue === previousValue) return
    void persistProjectVoiceDefaults()
  },
)

watch(
  () => globalMagpieVoice.value,
  (nextValue, previousValue) => {
    if (applyingProjectVoiceDefaults.value || nextValue === previousValue) return
    void persistProjectVoiceDefaults()
  },
)

watch(
  showTimeline,
  async isOpen => {
    if (isOpen) {
      await openTimelinePanel()
    } else {
      stopTimelinePlayback()
      teardownTimelineResizeObserver()
    }
  },
)

watch(
  () => playbackSpeed.value,
  speed => {
    if (!import.meta.client) return

    localStorage.setItem('narration-playback-speed', String(speed))

    document.querySelectorAll('audio').forEach(element => {
      ;(element as HTMLAudioElement).playbackRate = speed
    })
  },
)

watch(
  () => timelineZoomLevel.value,
  zoom => {
    const clamped = Math.max(MIN_TIMELINE_ZOOM_LEVEL, Math.min(MAX_TIMELINE_ZOOM_LEVEL, zoom))
    if (clamped !== zoom) {
      timelineZoomLevel.value = clamped
      return
    }

    if (!import.meta.client) return
    localStorage.setItem('narration-timeline-zoom-level', String(clamped))
  },
)

watch(
  () => timelineInnerWidth.value,
  () => {
    if (!showTimeline.value) return
    nextTick(() => {
      drawAllWaveforms()
      onTimelineScroll()
    })
  },
)

watch(
  () => segments.value.map(segment => `${segment.id}:${segment.status}:${segment.duration_seconds || 0}:${audioVersion[segment.id] || 0}`).join('|'),
  () => {
    if (!showTimeline.value) return
    nextTick(() => drawAllWaveforms())
  },
)

watch(
  transcriptions,
  () => {
    if (showTimeline.value) {
      nextTick(() => drawAllWaveforms())
    }

    if (expandedTrim.value !== null) {
      nextTick(() => drawTrimWaveform(expandedTrim.value as number))
    }
  },
  { deep: true },
)

watch(
  () => expandedTrim.value,
  segmentId => {
    if (segmentId === null) {
      resetTrimWaveformState()
      return
    }

    nextTick(() => {
      if (trimSegmentId.value === segmentId && trimWaveformData.value) {
        drawTrimWaveform(segmentId)
      } else {
        void loadTrimWaveform(segmentId)
      }
    })
  },
)

watch(
  () => showVoices.value,
  isOpen => {
    if (!isOpen || !voiceDraft.value) return
    nextTick(() => {
      if (voiceDraftWaveformData.value) {
        drawVoiceDraftWaveform()
      } else {
        void loadVoiceDraftWaveform()
      }
    })
  },
)

onMounted(() => {
  connectWs()

  if (import.meta.client) {
    const storedSpeed = Number(window.localStorage.getItem('narration-playback-speed'))
    if (!Number.isNaN(storedSpeed) && storedSpeed >= 0.5 && storedSpeed <= 2.5) {
      playbackSpeed.value = storedSpeed
    }

    const storedTimelineZoom = Number(window.localStorage.getItem('narration-timeline-zoom-level'))
    if (!Number.isNaN(storedTimelineZoom)) {
      timelineZoomLevel.value = Math.max(
        MIN_TIMELINE_ZOOM_LEVEL,
        Math.min(MAX_TIMELINE_ZOOM_LEVEL, storedTimelineZoom),
      )
    }

    document.addEventListener('play', onAnyAudioPlay, true)
  }

  void fetchMagpieVoices()
})

onUnmounted(() => {
  if (wsReconnectTimer) clearTimeout(wsReconnectTimer)
  if (ws) ws.close()
  resetTrimWaveformState()

  if (voiceDraft.value) {
    void discardVoiceDraft({ silent: true, skipConfirm: true })
  }

  stopTimelinePlayback()
  teardownTimelineResizeObserver()

  if (import.meta.client) {
    document.removeEventListener('play', onAnyAudioPlay, true)
  }

  if (audioContext) {
    audioContext.close().catch(() => {})
    audioContext = null
  }

  cancelTimelineAnimationLoop()
})
</script>

<template>
  <div class="space-y-4">
    <div
      v-if="status"
      class="rounded-md border p-3 text-sm"
      :class="error ? 'border-red-300 bg-red-50 text-red-700 dark:border-red-700 dark:bg-red-900/20 dark:text-red-300' : 'border-blue-300 bg-blue-50 text-blue-700 dark:border-blue-700 dark:bg-blue-900/20 dark:text-blue-300'"
    >
      <div class="flex items-center gap-2">
        <Loader2 v-if="generating" class="h-4 w-4 animate-spin" />
        <AlertCircle v-else-if="error" class="h-4 w-4" />
        <CheckCircle2 v-else class="h-4 w-4" />
        <span>{{ status }}</span>
        <span v-if="genEstimate" class="ml-auto text-xs opacity-70">~{{ genEstimate }}s</span>
      </div>
      <div v-if="generating && genTotal > 0" class="mt-2 h-1.5 overflow-hidden rounded bg-blue-200 dark:bg-blue-900/60">
        <div class="h-full bg-blue-500 transition-all duration-300" :style="{ width: `${genProgress}%` }" />
      </div>
    </div>

    <Card>
      <CardHeader class="pb-3">
        <CardTitle class="flex items-center gap-2 text-lg">
          <Mic2 class="h-5 w-5" />
          Narration Workspace
        </CardTitle>
        <CardDescription>
          Build and generate narration segments in this project.
        </CardDescription>
      </CardHeader>
      <CardContent class="space-y-3">
        <div class="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
          <span>{{ segments.length }} segments</span>
          <span>{{ doneCount }} done</span>
          <span>{{ pendingCount }} pending</span>
          <span>{{ studioVoiceCleanedCount }} studio voice cleaned</span>
          <span v-if="studioVoicePendingCount">{{ studioVoicePendingCount }} studio voice pending</span>
          <span v-if="queuedCount">{{ queuedCount }} queued</span>
          <span v-if="generatingCount">{{ generatingCount }} generating</span>
          <span v-if="errorCount">{{ errorCount }} failed</span>
          <span class="font-medium text-foreground">{{ totalDuration }}</span>
        </div>

        <div class="flex flex-wrap items-center gap-2">
          <Button size="sm" variant="outline" @click="showImport = !showImport">
            <Upload class="mr-1 h-4 w-4" />
            {{ showImport ? 'Hide Import' : 'Import' }}
          </Button>
          <Button size="sm" variant="outline" @click="showAdd = !showAdd">
            <Plus class="mr-1 h-4 w-4" />
            {{ showAdd ? 'Hide Add' : 'Add Segment' }}
          </Button>
          <Button size="sm" variant="outline" @click="openScriptEditor">
            Script Editor
          </Button>
          <Button size="sm" variant="outline" :disabled="!segments.length" @click="toggleTimeline">
            <Waves class="mr-1 h-4 w-4" />
            {{ showTimeline ? 'Hide Timeline' : 'Timeline' }}
          </Button>
          <Button size="sm" variant="outline" @click="showVoices = !showVoices">
            Voices
          </Button>
          <Button size="sm" variant="outline" @click="showExport = !showExport" :disabled="!hasAudio">
            Export
          </Button>

          <div class="mx-2 h-6 w-px bg-border" />

          <Button size="sm" :disabled="!segments.length || generating" @click="generateAll">
            Generate All
          </Button>
          <Button
            v-if="generating"
            size="sm"
            variant="destructive"
            :disabled="cancelling"
            @click="cancelGeneration"
          >
            {{ cancelling ? 'Cancelling...' : 'Cancel' }}
          </Button>
          <Button size="sm" variant="outline" :disabled="!errorCount || generating" @click="retryFailed">
            Retry Failed
          </Button>
          <Button size="sm" variant="outline" :disabled="!hasAudio || !!transcribeAllProgress" @click="transcribeAll">
            {{ transcribeAllProgress ? `Transcribing ${transcribeAllProgress.done}/${transcribeAllProgress.total}` : 'Transcribe All' }}
          </Button>
          <Button
            size="sm"
            variant="outline"
            :disabled="!studioVoicePendingCount || studioVoiceCleaningAll || generating"
            @click="cleanAllWithStudioVoice"
          >
            {{ studioVoiceCleanAllLabel }}
          </Button>

          <Button
            size="sm"
            variant="ghost"
            class="ml-auto"
            :class="confirmClear ? 'text-red-600' : ''"
            :disabled="!segments.length || generating"
            @click="clearAllSegments"
          >
            {{ confirmClear ? 'Confirm Clear' : 'Clear All' }}
          </Button>
        </div>

        <div class="flex flex-wrap items-center gap-2 rounded-md border bg-muted/20 p-2">
          <label class="text-xs text-muted-foreground">Filter</label>
          <select v-model="segmentStatusFilter" class="rounded border bg-background px-2 py-1 text-xs">
            <option value="all">All</option>
            <option value="pending">Pending</option>
            <option value="queued">Queued</option>
            <option value="generating">Generating</option>
            <option value="done">Done</option>
            <option value="error">Error</option>
          </select>
          <label class="ml-1 text-xs text-muted-foreground">Sort</label>
          <select v-model="segmentSortMode" class="rounded border bg-background px-2 py-1 text-xs">
            <option value="position">Segment Order</option>
            <option value="recent">Recently Generated</option>
          </select>
          <Button
            size="sm"
            :variant="showFinalSegments ? 'default' : 'outline'"
            class="h-8"
            @click="showFinalSegments = !showFinalSegments"
          >
            Show Final
          </Button>
          <Button
            size="sm"
            :variant="showNeedsReviewOnly ? 'default' : 'outline'"
            class="h-8"
            @click="showNeedsReviewOnly = !showNeedsReviewOnly"
          >
            Show Needs Review
          </Button>
          <Button
            v-if="segmentStatusFilter === 'done'"
            size="sm"
            :variant="doneTrimSuggestedOnly ? 'default' : 'outline'"
            class="h-8"
            :disabled="!trimSuggestedDoneCount && !doneTrimSuggestedOnly"
            @click="doneTrimSuggestedOnly = !doneTrimSuggestedOnly"
          >
            Trim Suggested {{ trimSuggestedDoneCount ? `(${trimSuggestedDoneCount})` : '' }}
          </Button>
          <Button
            size="sm"
            variant="outline"
            class="h-8"
            :disabled="!hasExpandedFilteredSegments"
            @click="collapseFilteredSegments"
          >
            Collapse All
          </Button>
          <Button
            size="sm"
            variant="outline"
            class="h-8"
            :disabled="!hasCollapsedFilteredSegments"
            @click="expandFilteredSegments"
          >
            Expand All
          </Button>
          <span class="ml-auto text-xs text-muted-foreground">{{ filteredSegments.length }} shown</span>
        </div>

        <div class="grid gap-2 sm:grid-cols-2">
          <div class="flex items-center gap-2 rounded-md border px-2 py-1.5">
            <label class="text-xs text-muted-foreground">Dia voice</label>
            <select v-model="globalVoiceSampleId" class="w-full rounded border bg-background px-2 py-1 text-xs">
              <option :value="null">Default</option>
              <option v-for="sample in voiceSamples" :key="sample.id" :value="sample.id">
                {{ sample.name }}
              </option>
            </select>
          </div>
          <div class="flex items-center gap-2 rounded-md border px-2 py-1.5">
            <label class="text-xs text-muted-foreground">Magpie voice</label>
            <select v-model="globalMagpieVoice" class="w-full rounded border bg-background px-2 py-1 text-xs">
              <option value="">Default</option>
              <option v-for="voice in magpieVoices" :key="voice" :value="voice">
                {{ voice }}
              </option>
            </select>
            <Button size="sm" variant="ghost" @click="fetchMagpieVoices">
              <RefreshCw class="h-4 w-4" />
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>

    <Card v-if="showImport">
      <CardHeader class="pb-3">
        <CardTitle class="text-base">Import</CardTitle>
      </CardHeader>
      <CardContent class="space-y-3">
        <div class="flex items-center gap-2">
          <Button size="sm" :variant="importMode === 'script' ? 'default' : 'outline'" @click="importMode = 'script'">
            Script
          </Button>
          <Button size="sm" :variant="importMode === 'article' ? 'default' : 'outline'" @click="importMode = 'article'">
            Article
          </Button>
          <select v-model="importService" class="ml-auto rounded border bg-background px-2 py-1 text-sm">
            <option value="dia">Dia</option>
            <option value="magpie">Magpie</option>
          </select>
        </div>

        <div v-if="importMode === 'script'" class="space-y-2">
          <Textarea
            v-model="importText"
            placeholder="Paste script here (one line per segment)"
            :rows="8"
          />
          <Button size="sm" :disabled="!importText.trim()" @click="doImportScript">
            Import Script
          </Button>
        </div>

        <div v-else class="space-y-2">
          <Textarea
            v-model="articleText"
            placeholder="Paste article text. It will be chunked and cleaned for narration."
            :rows="8"
          />
          <div class="flex flex-wrap items-center gap-2">
            <Button size="sm" :disabled="!articleText.trim() || articleProcessing" @click="processArticle">
              {{ articleProcessing ? 'Processing...' : 'Process Article' }}
            </Button>
            <Button size="sm" variant="outline" :disabled="!articleChunks.length" @click="acceptArticleSegments">
              Accept Segments
            </Button>
            <Button size="sm" variant="outline" :disabled="!articleChunks.some(chunk => chunk.error)" @click="retryAllFailedChunks">
              Retry Failed Chunks
            </Button>
            <span v-if="articleStatus" class="text-xs text-muted-foreground">{{ articleStatus }}</span>
          </div>

          <div v-if="articleChunks.length" class="space-y-2">
            <div
              v-for="(chunk, chunkIndex) in articleChunks"
              :key="`${chunkIndex}-${chunk.raw.slice(0, 20)}`"
              class="rounded-md border p-2"
              :class="chunk.error ? 'border-red-300' : 'border-border'"
            >
              <div class="mb-1 flex items-center gap-2 text-xs">
                <Badge variant="outline">Chunk {{ chunkIndex + 1 }}</Badge>
                <Badge v-if="chunk.error" variant="destructive">Error</Badge>
                <Badge v-else-if="chunk.processed" variant="secondary">Processed</Badge>
                <Button
                  v-if="chunk.error"
                  size="sm"
                  variant="ghost"
                  class="ml-auto h-6 px-2 text-xs"
                  :disabled="chunk.retrying"
                  @click="retryChunk(chunkIndex)"
                >
                  {{ chunk.retrying ? 'Retrying...' : 'Retry' }}
                </Button>
              </div>

              <div class="space-y-1">
                <div
                  v-for="(line, segmentIndex) in chunk.segments"
                  :key="`${chunkIndex}-${segmentIndex}`"
                  class="flex items-start gap-2 rounded bg-muted/50 px-2 py-1 text-sm"
                >
                  <span class="flex-1">{{ line }}</span>
                  <Button
                    size="sm"
                    variant="ghost"
                    class="h-6 px-2 text-xs"
                    :disabled="chunk.segments.length <= 1"
                    @click="removeArticleSegment(chunkIndex, segmentIndex)"
                  >
                    Remove
                  </Button>
                </div>
              </div>
            </div>
          </div>
        </div>
      </CardContent>
    </Card>

    <Card v-if="showScriptEditor">
      <CardHeader class="pb-3">
        <CardTitle class="text-base">Script Editor</CardTitle>
        <CardDescription>
          Edit all lines and sync against current segments.
        </CardDescription>
      </CardHeader>
      <CardContent class="space-y-2">
        <Textarea v-model="scriptText" :rows="10" />
        <div class="flex items-center gap-2">
          <Button size="sm" :disabled="scriptSyncing" @click="saveScript">
            {{ scriptSyncing ? 'Syncing...' : 'Sync Script' }}
          </Button>
          <Button size="sm" variant="outline" @click="showScriptEditor = false">
            Close
          </Button>
          <span v-if="scriptSyncStatus" class="text-xs text-muted-foreground">{{ scriptSyncStatus }}</span>
        </div>
      </CardContent>
    </Card>

    <Card v-if="showAdd">
      <CardHeader class="pb-3">
        <CardTitle class="text-base">Add Segment</CardTitle>
      </CardHeader>
      <CardContent class="space-y-2">
        <Textarea v-model="addText" placeholder="Segment text..." :rows="3" />
        <div class="flex items-center gap-2">
          <select v-model="addService" class="rounded border bg-background px-2 py-1 text-sm">
            <option value="dia">Dia</option>
            <option value="magpie">Magpie</option>
          </select>
          <Button size="sm" :disabled="!addText.trim()" @click="addSegment">
            Add
          </Button>
        </div>
      </CardContent>
    </Card>

    <Card v-if="showVoices">
      <CardHeader class="pb-3">
        <CardTitle class="text-base">Voice Samples</CardTitle>
        <CardDescription>
          Upload and manage Dia voice samples.
        </CardDescription>
      </CardHeader>
      <CardContent class="space-y-3">
        <div v-if="!voiceSamples.length" class="text-sm text-muted-foreground">
          No voice samples yet.
        </div>

        <div v-else class="grid gap-2">
          <div
            v-for="sample in voiceSamples"
            :key="sample.id"
            class="rounded-md border p-2"
          >
            <div class="mb-2 flex items-center justify-between gap-2">
              <div>
                <p class="text-sm font-medium">{{ sample.name }}</p>
              </div>
              <Button
                size="sm"
                variant="ghost"
                class="text-red-600"
                :disabled="voiceSampleSaving[sample.id]"
                @click="deleteVoiceSample(sample.id)"
              >
                Delete
              </Button>
            </div>

            <div class="mb-2 space-y-2">
              <Textarea
                v-model="voiceSampleTranscriptDrafts[sample.id]"
                :rows="3"
                placeholder="Voice sample text"
              />
              <Button
                size="sm"
                variant="outline"
                :disabled="voiceSampleSaving[sample.id] || (voiceSampleTranscriptDrafts[sample.id] ?? '') === sample.transcript"
                @click="saveVoiceSampleTranscript(sample.id)"
              >
                {{ voiceSampleSaving[sample.id] ? 'Saving...' : 'Save Text' }}
              </Button>
            </div>

            <audio :src="voiceSampleAudioUrl(sample.id)" controls preload="none" class="w-full" />
          </div>
        </div>

        <div class="space-y-3 border-t pt-3">
          <p class="text-xs text-muted-foreground">
            Upload a short audio or video clip. We extract audio, transcribe it, then let you trim and save.
          </p>

          <div class="grid gap-2 sm:grid-cols-[minmax(0,1fr)_auto]">
            <Input v-model="voiceName" placeholder="Voice name" />
            <div class="flex flex-wrap items-center gap-2">
              <input
                ref="voiceClipInput"
                type="file"
                accept="audio/*,video/*"
                class="text-sm"
                @change="onVoiceClipChange"
              >
              <Button size="sm" :disabled="!voiceClipFile || voiceDraftBusy" @click="uploadVoiceClip">
                {{ voiceDraftBusy ? 'Processing...' : (voiceDraft ? 'Replace Clip' : 'Upload Clip') }}
              </Button>
            </div>
          </div>

          <div
            v-if="voiceDraft"
            class="space-y-3 rounded-md border border-cyan-200 bg-cyan-50/30 p-3 dark:border-cyan-900/40 dark:bg-cyan-900/10"
          >
            <div class="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
              <span class="rounded border bg-background px-1.5 py-0.5 text-foreground">
                {{ voiceDraft.original_filename }}
              </span>
              <span class="tabular-nums">{{ voiceDraftTrimRangeLabel }}</span>
            </div>

            <audio
              :key="`voice-draft-audio-${voiceDraft.id}-${voiceDraftAudioVersion}`"
              :src="voiceSampleDraftAudioUrl(voiceDraft.id)"
              controls
              preload="none"
              class="w-full"
            />

            <div class="relative h-32 select-none">
              <canvas id="voice-draft-waveform" class="h-full w-full rounded-md border bg-muted/50" />

              <div
                class="trim-handle absolute bottom-0 top-0"
                :style="{ left: `${(voiceDraftTrimStartMs / voiceDraftDurationMs) * 100}%` }"
                @pointerdown="onVoiceDraftTrimPointerDown($event, 'start')"
              >
                <div class="h-full w-1 rounded-full bg-primary" />
                <div class="absolute -top-1 left-1/2 h-3 w-3 -translate-x-1/2 rounded-full border-2 border-background bg-primary" />
                <div class="absolute -bottom-1 left-1/2 h-3 w-3 -translate-x-1/2 rounded-full border-2 border-background bg-primary" />
              </div>

              <div
                class="trim-handle absolute bottom-0 top-0"
                :style="{ left: `${(voiceDraftTrimEndMs / voiceDraftDurationMs) * 100}%` }"
                @pointerdown="onVoiceDraftTrimPointerDown($event, 'end')"
              >
                <div class="h-full w-1 rounded-full bg-primary" />
                <div class="absolute -top-1 left-1/2 h-3 w-3 -translate-x-1/2 rounded-full border-2 border-background bg-primary" />
                <div class="absolute -bottom-1 left-1/2 h-3 w-3 -translate-x-1/2 rounded-full border-2 border-background bg-primary" />
              </div>

              <div
                class="pointer-events-none absolute bottom-0 left-0 top-0 rounded-l-md bg-black/15 dark:bg-white/10"
                :style="{ width: `${(voiceDraftTrimStartMs / voiceDraftDurationMs) * 100}%` }"
              />
              <div
                class="pointer-events-none absolute bottom-0 right-0 top-0 rounded-r-md bg-black/15 dark:bg-white/10"
                :style="{ width: `${100 - ((voiceDraftTrimEndMs / voiceDraftDurationMs) * 100)}%` }"
              />
            </div>

            <div v-if="voiceDraft.words?.length" class="flex flex-wrap gap-1">
              <span
                v-for="(word, index) in voiceDraft.words"
                :key="`voice-draft-word-${index}`"
                class="rounded px-1.5 py-0.5 text-[11px]"
                :class="word.start * 1000 >= voiceDraftTrimStartMs && word.end * 1000 <= voiceDraftTrimEndMs
                  ? 'bg-cyan-100 text-cyan-700 dark:bg-cyan-900/40 dark:text-cyan-300'
                  : 'bg-muted text-muted-foreground line-through'"
              >
                {{ word.word }}
              </span>
            </div>

            <div class="flex flex-wrap items-center gap-2">
              <Button size="sm" variant="outline" :disabled="voiceDraftBusy" @click="autoSuggestVoiceDraftTrim">
                Auto Trim
              </Button>
              <Button size="sm" variant="outline" :disabled="voiceDraftBusy" @click="applyVoiceDraftTrim">
                Trim + Re-Transcribe
              </Button>
              <Button size="sm" variant="outline" :disabled="voiceDraftBusy" @click="retranscribeVoiceDraft">
                Redo Transcription
              </Button>
              <Button size="sm" variant="ghost" class="text-red-600" :disabled="voiceDraftBusy" @click="discardVoiceDraft()">
                Discard Draft
              </Button>
            </div>

            <Textarea
              v-model="voiceDraftTranscript"
              :rows="4"
              placeholder="Transcription used for this voice sample"
            />

            <Button size="sm" :disabled="!canFinalizeVoiceDraft || voiceDraftBusy" @click="finalizeVoiceDraft">
              {{ voiceDraftBusy ? 'Working...' : 'Save Voice Sample' }}
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>

    <Card v-if="showExport">
      <CardHeader class="pb-3">
        <CardTitle class="text-base">Export</CardTitle>
      </CardHeader>
      <CardContent class="space-y-3">
        <div class="grid gap-3 sm:grid-cols-4">
          <div class="space-y-1">
            <label class="text-xs text-muted-foreground">Format</label>
            <select v-model="exportFormat" class="w-full rounded border bg-background px-2 py-1 text-sm">
              <option value="wav">WAV</option>
              <option value="mp3">MP3</option>
            </select>
          </div>
          <div class="space-y-1">
            <label class="text-xs text-muted-foreground">Gap (ms)</label>
            <Input v-model.number="exportGapMs" type="number" min="0" max="5000" />
          </div>
          <div class="space-y-1">
            <label class="text-xs text-muted-foreground">Fade (ms)</label>
            <Input v-model.number="exportFadeMs" type="number" min="0" max="500" />
          </div>
          <div class="flex items-end gap-2">
            <label class="inline-flex items-center gap-2 text-sm">
              <input v-model="exportNormalize" type="checkbox">
              Normalize
            </label>
            <Button size="sm" :disabled="!hasAudio" @click="exportAudio">
              Download Combined
            </Button>
          </div>
        </div>
        <div class="flex items-center justify-between border-t pt-3">
          <p class="text-sm text-muted-foreground">
            Download individual segment files as a zip archive
          </p>
          <Button size="sm" variant="outline" :disabled="!hasAudio" @click="exportAudioZip">
            Download Zip
          </Button>
        </div>
      </CardContent>
    </Card>

    <Card v-if="showTimeline && segments.length">
      <CardHeader class="pb-2">
        <div class="flex flex-wrap items-center gap-2">
          <CardTitle class="text-base">Timeline</CardTitle>
          <span class="text-xs text-muted-foreground tabular-nums">{{ formatDuration(timelineTotalSeconds) }}</span>

          <Button size="sm" variant="outline" :disabled="!timelineHasDoneSegments" @click="toggleTimelinePlayPause">
            <Play v-if="!timelineIsPlaying" class="mr-1 h-3.5 w-3.5" />
            <Pause v-else class="mr-1 h-3.5 w-3.5" />
            {{ timelineIsPlaying ? 'Pause' : 'Play All' }}
          </Button>

          <Button v-if="timelinePlayingIdx >= 0" size="sm" variant="outline" @click="stopTimelinePlayback">
            Stop
          </Button>

          <div class="ml-auto flex items-center gap-2">
            <label class="text-xs text-muted-foreground">Speed</label>
            <input
              v-model.number="playbackSpeed"
              type="range"
              min="0.5"
              max="2.5"
              step="0.05"
              class="h-1.5 w-24 accent-primary"
            >
            <span class="w-10 text-right text-xs tabular-nums text-muted-foreground">{{ playbackSpeed.toFixed(1) }}x</span>

            <div class="mx-1 h-5 w-px bg-border" />

            <label class="text-xs text-muted-foreground">Zoom</label>
            <input
              v-model.number="timelineZoomLevel"
              type="range"
              :min="MIN_TIMELINE_ZOOM_LEVEL"
              :max="MAX_TIMELINE_ZOOM_LEVEL"
              step="0.05"
              class="h-1.5 w-24 accent-primary"
            >
            <span class="w-12 text-right text-xs tabular-nums text-muted-foreground">{{ timelineZoomLevel.toFixed(2) }}x</span>
          </div>
        </div>

        <CardDescription v-if="timelinePlayingIdx >= 0" class="tabular-nums">
          {{ formatDuration((timelineOffsets[timelinePlayingIdx] || 0) + timelineCurrentTime) }} / {{ formatDuration(timelineTotalSeconds) }}
          • Segment {{ timelinePlayingIdx + 1 }} of {{ segments.length }}
        </CardDescription>
      </CardHeader>

      <CardContent class="space-y-2">
        <div
          v-if="Object.keys(transcriptions).length"
          ref="wordTrackScrollEl"
          class="timeline-scroll overflow-x-auto whitespace-nowrap rounded-md border bg-muted/30 px-3 py-1.5"
        >
          <template v-for="(segment, segmentIndex) in segments" :key="`wt-${segment.id}`">
            <template v-if="transcriptions[segment.id]?.words?.length">
              <span
                v-for="(word, wordIndex) in transcriptions[segment.id].words"
                :key="`wt-${segment.id}-${wordIndex}`"
                class="mr-0.5 inline-block rounded px-0.5 text-sm transition-colors"
                :class="[
                  timelinePlayingIdx === segmentIndex && timelineCurrentTime >= word.start && timelineCurrentTime <= word.end
                    ? 'word-active bg-primary/20 font-semibold text-primary'
                    : timelinePlayingIdx === segmentIndex && timelineCurrentTime > word.end
                      ? 'text-muted-foreground/60'
                      : timelinePlayingIdx > segmentIndex
                        ? 'text-muted-foreground/60'
                        : 'text-muted-foreground',
                ]"
              >
                {{ word.word }}
              </span>
            </template>
            <span v-else-if="segment.status === 'done'" class="text-xs italic text-muted-foreground/50">...</span>
            <span v-if="segmentIndex < segments.length - 1" class="mx-1 text-[10px] text-muted-foreground/50">|</span>
          </template>
        </div>

        <div
          ref="timelineScrollEl"
          class="timeline-scroll relative overflow-x-auto overflow-y-hidden rounded-md border bg-muted/35"
          style="height: 72px;"
          @scroll="onTimelineScroll"
        >
          <div class="relative flex h-full" :style="{ width: `${timelineInnerWidth}%` }">
            <button
              v-for="(segment, index) in segments"
              :key="segment.id"
              type="button"
              class="relative h-full cursor-pointer border-r border-white/20 text-left transition-shadow last:border-r-0 dark:border-black/20"
              :style="{ width: `${timelineWidths[index]}%`, minWidth: '6px' }"
              :class="[
                segment.status === 'done'
                  ? 'bg-emerald-200/60 dark:bg-emerald-900/45'
                  : segment.status === 'error'
                    ? 'bg-red-200/60 dark:bg-red-900/45'
                    : segment.status === 'generating'
                      ? 'bg-amber-200/60 dark:bg-amber-900/45'
                      : 'bg-slate-200/70 dark:bg-slate-700/40',
                timelinePlayingIdx === index ? 'z-10 ring-2 ring-primary ring-inset' : '',
              ]"
              @click="timelineClickSegment(index)"
            >
              <canvas :id="`waveform-${segment.id}`" class="absolute inset-0 h-full w-full pointer-events-none" />
              <span class="absolute bottom-0.5 left-1 text-[10px] font-semibold text-black/40 dark:text-white/40">{{ segment.position }}</span>
            </button>

            <div
              v-if="timelinePlayingIdx >= 0"
              class="pointer-events-none absolute bottom-0 top-0"
              :style="{ left: `${timelineCursorPercent}%` }"
            >
              <div class="ml-[-1px] h-full w-0.5 bg-primary" />
              <div class="absolute -top-1 left-1/2 h-2.5 w-2.5 -translate-x-1/2 rounded-full border-2 border-background bg-primary" />
            </div>
          </div>
        </div>

        <div
          v-if="timelineZoom > 1"
          class="relative mt-1 h-5 cursor-pointer overflow-hidden rounded border bg-muted/35"
          @click="onMinimapClick"
        >
          <div class="flex h-full">
            <div
              v-for="(segment, index) in segments"
              :key="`mm-${segment.id}`"
              :style="{ width: `${timelineWidths[index]}%` }"
              class="h-full border-r border-white/20 last:border-r-0 dark:border-black/20"
              :class="[
                segment.status === 'done'
                  ? 'bg-emerald-300/50 dark:bg-emerald-900/35'
                  : segment.status === 'error'
                    ? 'bg-red-300/50 dark:bg-red-900/35'
                    : 'bg-slate-300/50 dark:bg-slate-700/35',
              ]"
            />
          </div>

          <div
            class="absolute bottom-0 top-0 rounded-sm border-2 border-primary/70 bg-primary/10"
            :style="{
              left: `${timelineViewportLeft * 100}%`,
              width: `${timelineViewportRatio * 100}%`,
            }"
          />

          <div
            v-if="timelinePlayingIdx >= 0"
            class="pointer-events-none absolute bottom-0 top-0"
            :style="{ left: `${timelineCursorPercent}%` }"
          >
            <div class="ml-[-1px] h-full w-0.5 bg-primary" />
          </div>
        </div>

        <audio
          ref="timelineAudioPlayer"
          class="hidden"
          @ended="onTimelineAudioEnded"
          @timeupdate="onTimelineTimeUpdate"
        />
      </CardContent>
    </Card>

    <div v-if="loading && !segments.length" class="flex items-center justify-center py-8 text-sm text-muted-foreground">
      <Loader2 class="mr-2 h-4 w-4 animate-spin" />
      Loading narration segments...
    </div>

    <div v-else-if="!segments.length" class="rounded-md border border-dashed p-8 text-center text-sm text-muted-foreground">
      No narration segments yet. Import a script or add one manually.
    </div>

    <div v-else class="space-y-3">
      <div
        v-if="!filteredSegments.length"
        class="rounded-md border border-dashed p-6 text-center text-sm text-muted-foreground"
      >
        No segments match the current filters.
      </div>

      <template v-for="segment in filteredSegments" :key="`segment-wrap-${segment.id}`">
        <div class="group relative -my-1">
          <button
            v-if="insertAtPosition !== segment.position"
            type="button"
            class="flex h-8 w-full items-center justify-center rounded-md border border-dashed border-transparent text-xs text-muted-foreground opacity-100 transition hover:border-primary/40 hover:bg-primary/5 hover:text-primary sm:opacity-0 sm:group-hover:opacity-100"
            @click="startInsert(segment.position)"
          >
            + Insert segment here
          </button>
          <div
            v-else
            class="space-y-2 rounded-md border border-dashed border-primary/40 bg-primary/5 p-3"
          >
            <Textarea v-model="insertText" placeholder="New segment text..." :rows="3" />
            <div class="flex flex-wrap items-center gap-2">
              <select v-model="insertService" class="rounded border bg-background px-2 py-1 text-sm">
                <option value="dia">Dia</option>
                <option value="magpie">Magpie</option>
              </select>
              <Button size="sm" :disabled="!insertText.trim()" @click="insertSegment">
                Insert
              </Button>
              <Button size="sm" variant="outline" @click="cancelInsert">
                Cancel
              </Button>
              <span class="text-xs text-muted-foreground">Position {{ segment.position }}</span>
            </div>
          </div>
        </div>

        <Card :class="isSegmentCollapsed(segment.id) ? 'gap-2 py-2' : ''">
        <CardHeader
          :class="isSegmentCollapsed(segment.id) ? 'cursor-pointer px-4 pb-1' : 'cursor-pointer pb-3'"
          :title="isSegmentCollapsed(segment.id) ? 'Click to expand' : 'Click to collapse'"
          @click="toggleSegmentCollapsed(segment.id)"
        >
          <div
            class="flex flex-wrap justify-between gap-2"
            :class="isSegmentCollapsed(segment.id) ? 'items-center' : 'items-start'"
          >
            <div :class="isSegmentCollapsed(segment.id) ? 'space-y-0.5' : 'space-y-1'">
              <div class="flex items-center gap-2">
                <Badge variant="outline">#{{ segment.position }}</Badge>
                <span class="rounded px-2 py-0.5 text-xs font-medium" :class="statusClass(segmentDisplayStatus(segment))">
                  {{ segmentDisplayStatus(segment) }}
                </span>
                <Badge
                  v-if="segment.is_final"
                  variant="secondary"
                  class="bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300"
                >
                  Final
                </Badge>
                <Badge
                  v-if="segment.needs_review"
                  variant="secondary"
                  class="bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300"
                >
                  Needs Review
                </Badge>
                <span
                  v-if="segment.audio_path"
                  class="rounded px-2 py-0.5 text-xs font-medium"
                  :class="studioVoiceStatusClass(segment.studio_voice_status)"
                >
                  Studio Voice: {{ studioVoiceStatusLabel(segment.studio_voice_status) }}
                </span>
                <Badge v-if="segment.status === 'done' && segmentNeedsTrim(segment)" variant="secondary" class="text-cyan-700 dark:text-cyan-300">
                  Trim suggested
                </Badge>
              </div>

              <p v-if="isSegmentCollapsed(segment.id)" class="max-w-3xl text-sm leading-snug text-muted-foreground">
                {{ segmentPreviewText(segment.text) }}
              </p>

              <div v-if="segment.error_message" class="flex items-center gap-1 text-xs text-red-600 dark:text-red-400">
                <XCircle class="h-3 w-3" />
                {{ segment.error_message }}
              </div>
              <div
                v-if="segment.studio_voice_error_message"
                class="flex items-center gap-1 text-xs text-amber-700 dark:text-amber-300"
              >
                <AlertCircle class="h-3 w-3" />
                {{ segment.studio_voice_error_message }}
              </div>

              <div
                v-if="isSegmentCollapsed(segment.id) && segment.audio_path"
                class="pt-1"
                @click.stop
                @pointerdown.stop
              >
                <audio
                  :key="`segment-audio-inline-${segment.id}-${audioVersion[segment.id] || 0}`"
                  :src="segmentAudioUrl(segment.id)"
                  controls
                  preload="none"
                  class="w-full max-w-xl"
                />
              </div>
            </div>

            <div class="flex items-center gap-2" @click.stop>
              <select
                :value="segment.service"
                class="rounded border bg-background px-2 py-1 text-xs"
                @change="onSegmentServiceChange(segment, $event)"
              >
                <option value="dia">Dia</option>
                <option value="magpie">Magpie</option>
              </select>

              <Button size="sm" variant="outline" class="h-8 px-2" @click="moveSegment(segment.id, -1)">
                ↑
              </Button>
              <Button size="sm" variant="outline" class="h-8 px-2" @click="moveSegment(segment.id, 1)">
                ↓
              </Button>
              <Button size="sm" variant="outline" class="h-8 px-2" @click="toggleSegmentCollapsed(segment.id)">
                {{ isSegmentCollapsed(segment.id) ? 'Expand' : 'Collapse' }}
              </Button>
            </div>
          </div>
        </CardHeader>

        <CardContent v-if="!isSegmentCollapsed(segment.id)" class="space-y-3">
          <div v-if="editingId === segment.id" class="space-y-2">
            <Textarea v-model="editText" :rows="3" />
            <div class="flex items-center gap-2">
              <Button size="sm" @click="saveEdit(segment.id)">Save</Button>
              <Button size="sm" variant="outline" @click="editingId = null">Cancel</Button>
            </div>
          </div>

          <div v-else>
            <p class="text-sm leading-relaxed">{{ segment.text }}</p>
            <p v-if="segment.original_text" class="mt-1 text-xs text-muted-foreground">
              Original: {{ segment.original_text }}
            </p>
          </div>

          <div class="flex flex-wrap items-center gap-2">
            <Button size="sm" variant="outline" @click="startEdit(segment)">
              Edit
            </Button>
            <Button
              size="sm"
              variant="outline"
              :disabled="generating"
              @click="openSplitPreview(segment.id)"
            >
              {{ splitSegmentId === segment.id ? 'Hide Split' : 'Split' }}
            </Button>
            <Button size="sm" variant="outline" class="text-red-600" @click="deleteSegment(segment.id)">
              Delete
            </Button>
            <Button size="sm" @click="generateOne(segment.id)">
              Generate
            </Button>
            <Button size="sm" variant="outline" @click="regenerate(segment.id)">
              Regenerate
            </Button>
            <Button
              v-if="segment.status === 'error'"
              size="sm"
              variant="outline"
              :disabled="!segment.audio_path"
              @click="markSegmentDone(segment)"
            >
              Mark Done
            </Button>
            <Button
              size="sm"
              :variant="segment.is_final ? 'default' : 'outline'"
              @click="toggleFinal(segment)"
            >
              {{ segment.is_final ? 'Final' : 'Mark Final' }}
            </Button>
            <Button
              size="sm"
              :variant="segment.needs_review ? 'default' : 'outline'"
              :disabled="!segment.needs_review"
              @click="clearNeedsReview(segment)"
            >
              Needs Review
            </Button>
            <Button size="sm" variant="outline" @click="toggleVariants(segment.id)">
              Variants
            </Button>
            <Button
              v-if="segmentHasTrimmableAudio(segment)"
              size="sm"
              variant="outline"
              :class="expandedTrim === segment.id ? 'border-cyan-500 text-cyan-700 dark:text-cyan-300' : ''"
              @click="toggleTrim(segment.id)"
            >
              <Scissors class="mr-1 h-3.5 w-3.5" />
              {{ expandedTrim === segment.id ? 'Hide Trim' : 'Trim Deadspace' }}
            </Button>
            <Button
              size="sm"
              variant="outline"
              :disabled="!segment.audio_path || !!transcribing[segment.id]"
              @click="transcribeSegment(segment.id)"
            >
              {{ transcribing[segment.id] ? 'Transcribing...' : 'Transcribe' }}
            </Button>
            <Button
              v-if="transcriptions[segment.id]"
              size="sm"
              variant="outline"
              @click="toggleTranscript(segment.id)"
            >
              {{ expandedTranscript === segment.id ? 'Hide Transcript' : 'Transcript' }}
            </Button>
          </div>

          <div
            v-if="splitSegmentId === segment.id"
            class="space-y-3 rounded-md border border-indigo-200 bg-indigo-50/40 p-3 dark:border-indigo-900/50 dark:bg-indigo-900/10"
          >
            <div class="flex flex-wrap items-center gap-2">
              <p class="text-sm font-medium text-indigo-700 dark:text-indigo-300">Split Segment</p>
              <label class="text-xs text-muted-foreground">Target words</label>
              <Input
                v-model.number="splitTargetWords"
                type="number"
                class="h-8 w-24"
                :min="MIN_SPLIT_TARGET_WORDS"
                :max="MAX_SPLIT_TARGET_WORDS"
                @change="refreshSplitPreview(segment.id)"
              />
              <Button
                size="sm"
                variant="outline"
                :disabled="splitPreviewLoading || splitApplying"
                @click="refreshSplitPreview(segment.id)"
              >
                {{ splitPreviewLoading ? 'Previewing...' : 'Refresh Preview' }}
              </Button>
              <Button
                size="sm"
                :disabled="splitPreviewLoading || splitApplying || !splitPreview?.can_split"
                @click="applySegmentSplit(segment.id)"
              >
                {{ splitApplying ? 'Splitting...' : 'Confirm Split' }}
              </Button>
              <Button size="sm" variant="outline" @click="resetSplitState({ keepTarget: true })">
                Cancel
              </Button>
            </div>

            <p v-if="splitPreview" class="text-xs text-muted-foreground">
              {{ splitPreview.groups.length }} groups previewed · target {{ splitPreview.target_words }} words ({{ splitPreview.min_words }}-{{ splitPreview.max_words }} ideal)
            </p>
            <p v-if="splitPreview && !splitPreview.can_split" class="text-xs text-amber-700 dark:text-amber-300">
              This segment does not split into multiple sentence groups with the current settings.
            </p>

            <div v-if="splitPreview?.groups?.length" class="space-y-2">
              <div
                v-for="(group, groupIndex) in splitPreview.groups"
                :key="`split-group-${segment.id}-${groupIndex}`"
                class="rounded border bg-background/80 p-2"
              >
                <div class="mb-1 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                  <Badge variant="outline">Segment {{ groupIndex + 1 }}</Badge>
                  <span>{{ group.word_count }} words</span>
                  <span>{{ group.sentence_count }} sentence{{ group.sentence_count === 1 ? '' : 's' }}</span>
                </div>
                <p class="text-sm leading-relaxed">{{ group.text }}</p>
              </div>
            </div>
          </div>

          <Input
            v-model="regenText[segment.id]"
            placeholder="Optional regenerate text override"
          />

          <div v-if="segment.audio_path" class="space-y-2">
            <div class="space-y-1">
              <p class="text-xs font-medium text-muted-foreground">Original</p>
              <audio
                :key="`segment-audio-${segment.id}-${audioVersion[segment.id] || 0}`"
                :src="segmentAudioUrl(segment.id)"
                controls
                preload="none"
                class="w-full"
              />
            </div>
            <div v-if="segment.studio_voice_audio_path" class="space-y-1">
              <p class="text-xs font-medium text-emerald-700 dark:text-emerald-300">Studio Voice</p>
              <audio
                :key="`segment-audio-cleaned-${segment.id}-${audioVersion[segment.id] || 0}`"
                :src="segmentCleanedAudioUrl(segment.id)"
                controls
                preload="none"
                class="w-full"
              />
            </div>
          </div>

          <div
            v-if="expandedTrim === segment.id"
            class="space-y-3 rounded-md border border-cyan-200 bg-cyan-50/40 p-3 dark:border-cyan-900/50 dark:bg-cyan-900/10"
          >
            <div class="flex flex-wrap items-center gap-2">
              <p class="text-sm font-medium text-cyan-700 dark:text-cyan-300">Trim Deadspace</p>
              <span class="text-xs tabular-nums text-muted-foreground">{{ trimRangeLabel }}</span>

              <Button
                size="sm"
                variant="outline"
                :class="trimSelectionArmed ? 'border-rose-500 text-rose-700 dark:text-rose-300' : ''"
                :disabled="trimWaveformLoading || !trimWaveformData || trimApplying"
                @click="beginTrimSelection"
              >
                {{ trimSelectionArmed ? 'Drag on Waveform' : 'Select Deadspace' }}
              </Button>
              <Button
                size="sm"
                variant="outline"
                :disabled="trimWaveformLoading || !trimWaveformData || !hasTrimSelection || !trimDecodedBuffer"
                @click="previewTrim"
              >
                Preview New Audio
              </Button>
              <Button
                size="sm"
                :disabled="trimApplying || trimWaveformLoading || !trimWaveformData || !hasTrimSelection"
                @click="applyTrim"
              >
                {{ trimApplying ? 'Saving...' : 'Save' }}
              </Button>
              <Button
                size="sm"
                variant="outline"
                :disabled="trimWaveformLoading || !hasTrimSelection"
                @click="clearTrimSelection"
              >
                Clear
              </Button>
              <Button size="sm" variant="outline" :disabled="trimApplying" @click="cancelTrimDeadspace">
                Cancel
              </Button>
              <Button
                size="sm"
                variant="outline"
                :disabled="trimWaveformLoading || trimApplying"
                @click="regenerateTrimWaveform(segment.id)"
              >
                Regenerate Waveform
              </Button>
              <Button
                v-if="trimWaveformError"
                size="sm"
                variant="outline"
                :disabled="trimWaveformLoading"
                @click="loadTrimWaveform(segment.id)"
              >
                Retry Waveform
              </Button>
            </div>
            <p v-if="trimWaveformLoading" class="text-xs text-muted-foreground">Loading waveform...</p>
            <p v-else-if="trimWaveformError" class="text-xs text-amber-700 dark:text-amber-300">{{ trimWaveformError }}</p>
            <p v-else-if="trimWaveformData && !trimDecodedBuffer" class="text-xs text-muted-foreground">
              Waveform loaded in server mode. Preview is unavailable, but you can still save trims.
            </p>
            <p v-else class="text-xs text-muted-foreground">
              {{ trimSelectionArmed
                ? 'Click and drag on the waveform to highlight deadspace to remove.'
                : 'Click Select Deadspace, drag to highlight the section to cut, then preview or save.' }}
            </p>

            <div class="relative h-32 select-none">
              <canvas :id="`trim-waveform-${segment.id}`" class="h-full w-full rounded-md border bg-muted/50" />

              <div
                v-if="trimWaveformData"
                class="absolute inset-0 rounded-md touch-none"
                :class="trimSelectionArmed ? 'cursor-crosshair' : 'cursor-default'"
                @pointerdown="onTrimWaveformPointerDown($event, segment.id)"
              >
                <span class="sr-only">Trim selection area</span>
              </div>

              <div
                v-if="hasTrimSelection"
                class="pointer-events-none absolute bottom-0 top-0 rounded-md border border-rose-500/70 bg-rose-500/20"
                :style="{
                  left: `${(trimSelectionStart / trimAudioDuration) * 100}%`,
                  width: `${(trimSelectionDuration / trimAudioDuration) * 100}%`,
                }"
              />
            </div>

            <div v-if="transcriptions[segment.id]?.words?.length" class="flex flex-wrap gap-1">
              <span
                v-for="(word, index) in transcriptions[segment.id].words"
                :key="`trim-word-${segment.id}-${index}`"
                class="rounded px-1.5 py-0.5 text-[11px]"
                :class="hasTrimSelection && word.start * 1000 >= trimSelectionStart && word.end * 1000 <= trimSelectionEnd
                  ? 'bg-rose-100 text-rose-700 line-through dark:bg-rose-900/40 dark:text-rose-300'
                  : 'bg-cyan-100 text-cyan-700 dark:bg-cyan-900/40 dark:text-cyan-300'"
              >
                {{ word.word }}
              </span>
            </div>
          </div>

          <div v-if="expandedVariants === segment.id" class="space-y-2 rounded-md border bg-muted/30 p-3">
            <div class="flex items-center gap-2 text-sm font-medium">
              <Waves class="h-4 w-4" />
              Variants
            </div>
            <div v-if="!variantsMap[segment.id]?.length" class="text-xs text-muted-foreground">
              No variants yet.
            </div>
            <div v-else class="space-y-2">
              <div
                v-for="variant in variantsMap[segment.id]"
                :key="variant.id"
                class="rounded border bg-background p-2"
              >
                <div class="mb-1 flex items-center justify-between gap-2 text-xs">
                  <span>#{{ variant.id }} · {{ variant.service }} · Studio Voice: {{ studioVoiceStatusLabel(variant.studio_voice_status) }}</span>
                  <div class="flex items-center gap-2">
                    <Button size="sm" variant="outline" class="h-7 px-2" @click="selectVariant(segment.id, variant.id)">
                      Select
                    </Button>
                    <Button size="sm" variant="ghost" class="h-7 px-2 text-red-600" @click="deleteVariant(variant)">
                      Delete
                    </Button>
                  </div>
                </div>
                <p v-if="variant.studio_voice_error_message" class="mb-1 text-[11px] text-amber-700 dark:text-amber-300">
                  {{ variant.studio_voice_error_message }}
                </p>
                <div class="space-y-1">
                  <p class="text-[11px] font-medium text-muted-foreground">Original</p>
                  <audio :src="variantAudioUrl(variant.id)" controls preload="none" class="w-full" />
                </div>
                <div v-if="variant.studio_voice_audio_path" class="mt-2 space-y-1">
                  <p class="text-[11px] font-medium text-emerald-700 dark:text-emerald-300">Studio Voice</p>
                  <audio :src="variantCleanedAudioUrl(variant.id)" controls preload="none" class="w-full" />
                </div>
              </div>
            </div>
          </div>

          <div v-if="expandedTranscript === segment.id && transcriptions[segment.id]" class="space-y-2 rounded-md border bg-muted/30 p-3">
            <div class="flex items-center justify-between">
              <p class="text-sm font-medium">Transcription</p>
              <Button size="sm" variant="ghost" class="h-7 px-2 text-red-600" @click="deleteTranscription(segment.id)">
                Delete
              </Button>
            </div>
            <p class="text-sm">{{ transcriptions[segment.id].text }}</p>
            <div v-if="transcriptions[segment.id].words?.length" class="flex flex-wrap gap-1">
              <button
                v-for="(word, index) in transcriptions[segment.id].words"
                :key="`${segment.id}-word-${index}`"
                type="button"
                class="rounded border px-1.5 py-0.5 text-xs transition-colors"
                :class="getActiveWordIdx(segment.id) === index
                  ? 'border-primary bg-primary text-primary-foreground'
                  : 'border-border bg-background hover:bg-muted'"
                :title="`${word.start.toFixed(2)}s - ${word.end.toFixed(2)}s`"
                @click="seekToWord(segment.id, word.start)"
              >
                {{ word.word }}
              </button>
            </div>
          </div>
        </CardContent>
        </Card>
      </template>

      <div class="group relative -my-1">
        <button
          v-if="insertAtPosition !== segments.length + 1"
          type="button"
          class="flex h-8 w-full items-center justify-center rounded-md border border-dashed border-transparent text-xs text-muted-foreground opacity-100 transition hover:border-primary/40 hover:bg-primary/5 hover:text-primary sm:opacity-0 sm:group-hover:opacity-100"
          @click="startInsert(segments.length + 1)"
        >
          + Insert segment at end
        </button>
        <div
          v-else
          class="space-y-2 rounded-md border border-dashed border-primary/40 bg-primary/5 p-3"
        >
          <Textarea v-model="insertText" placeholder="New segment text..." :rows="3" />
          <div class="flex flex-wrap items-center gap-2">
            <select v-model="insertService" class="rounded border bg-background px-2 py-1 text-sm">
              <option value="dia">Dia</option>
              <option value="magpie">Magpie</option>
            </select>
            <Button size="sm" :disabled="!insertText.trim()" @click="insertSegment">
              Insert
            </Button>
            <Button size="sm" variant="outline" @click="cancelInsert">
              Cancel
            </Button>
            <span class="text-xs text-muted-foreground">Position {{ segments.length + 1 }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.timeline-scroll::-webkit-scrollbar {
  display: none;
}

.timeline-scroll {
  -ms-overflow-style: none;
  scrollbar-width: none;
}

.trim-handle {
  cursor: ew-resize;
  touch-action: none;
}
</style>
