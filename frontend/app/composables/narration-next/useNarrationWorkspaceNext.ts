import {
  computed,
  onMounted,
  onUnmounted,
  reactive,
  ref,
  watch,
  type Ref,
} from 'vue'
import type {
  NarrationSegment,
  NarrationService,
  NarrationTranscription,
} from '~/types'
import { useApi } from '~/composables/useApi'
import {
  filterSegments,
  formatDuration,
  resolveSegmentDisplayStatus,
  segmentDurationSeconds,
  sortSegments,
  type SegmentSortMode,
  type SegmentStatusFilter,
} from './narrationWorkspaceUtils'

interface TranscribeAllProgress {
  done: number
  total: number
}

function asErrorMessage(err: any, fallback: string) {
  return err?.data?.detail || err?.message || fallback
}

export function useNarrationWorkspaceNext(projectId: Ref<string>) {
  const { baseURL } = useApi()

  const loading = ref(false)
  const error = ref<string | null>(null)
  const status = ref('')

  const segments = ref<NarrationSegment[]>([])
  const transcriptions = reactive<Record<number, NarrationTranscription>>({})
  const transcribing = reactive<Record<number, boolean>>({})
  const audioVersion = reactive<Record<number, number>>({})
  const queuedSegmentIds = reactive(new Set<number>())

  const editingId = ref<number | null>(null)
  const editText = ref('')
  const expandedTranscript = ref<number | null>(null)
  const regenText = reactive<Record<number, string>>({})

  const showImport = ref(false)
  const showAdd = ref(false)
  const showTimeline = ref(false)
  const showExport = ref(false)

  const importText = ref('')
  const importService = ref<NarrationService>('dia')
  const addText = ref('')
  const addService = ref<NarrationService>('dia')

  const exportFormat = ref<'wav' | 'mp3'>('wav')
  const exportGapMs = ref(750)
  const exportFadeMs = ref(50)
  const exportNormalize = ref(true)

  const generating = ref(false)
  const cancelling = ref(false)
  const genIndex = ref(0)
  const genTotal = ref(0)
  const genEstimate = ref<number | null>(null)

  const segmentStatusFilter = ref<SegmentStatusFilter>('all')
  const segmentSortMode = ref<SegmentSortMode>('position')
  const showFinalSegments = ref(true)
  const showNeedsReviewOnly = ref(false)

  const transcribeAllProgress = ref<TranscribeAllProgress | null>(null)

  let ws: WebSocket | null = null
  let wsReconnectTimer: ReturnType<typeof setTimeout> | null = null
  let fetchSegmentsRequestId = 0

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

  const pendingCount = computed(() => segments.value.filter(segment => resolveSegmentDisplayStatus(segment, queuedSegmentIds) === 'pending').length)
  const queuedCount = computed(() => segments.value.filter(segment => resolveSegmentDisplayStatus(segment, queuedSegmentIds) === 'queued').length)
  const generatingCount = computed(() => segments.value.filter(segment => resolveSegmentDisplayStatus(segment, queuedSegmentIds) === 'generating').length)
  const doneCount = computed(() => segments.value.filter(segment => resolveSegmentDisplayStatus(segment, queuedSegmentIds) === 'done').length)
  const errorCount = computed(() => segments.value.filter(segment => resolveSegmentDisplayStatus(segment, queuedSegmentIds) === 'error').length)

  const filteredSegments = computed(() => filterSegments({
    segments: segments.value,
    queuedIds: queuedSegmentIds,
    statusFilter: segmentStatusFilter.value,
    sortMode: segmentSortMode.value,
    showFinalSegments: showFinalSegments.value,
    showNeedsReviewOnly: showNeedsReviewOnly.value,
  }))

  const hasAudio = computed(() => (
    segments.value.some(segment => !!segment.audio_path || !!segment.studio_voice_audio_path)
  ))

  const genProgress = computed(() => {
    if (!genTotal.value) return 0
    return Math.max(0, Math.min(100, (genIndex.value / genTotal.value) * 100))
  })

  const totalDuration = computed(() => {
    const seconds = segments.value.reduce((sum, segment) => sum + segmentDurationSeconds(segment), 0)
    return formatDuration(seconds)
  })

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

  function segmentAudioUrl(segmentId: number) {
    return `${baseURL}/api/segments/${segmentId}/audio?v=${audioVersion[segmentId] || 0}`
  }

  function segmentCleanedAudioUrl(segmentId: number) {
    return `${baseURL}/api/segments/${segmentId}/audio/cleaned?v=${audioVersion[segmentId] || 0}`
  }

  function segmentPreferredAudioUrl(segment: NarrationSegment) {
    if (segment.studio_voice_audio_path) {
      return segmentCleanedAudioUrl(segment.id)
    }
    return segmentAudioUrl(segment.id)
  }

  function clearSegmentTransientState(segmentId: number) {
    delete transcriptions[segmentId]
    delete transcribing[segmentId]
    delete audioVersion[segmentId]
    delete regenText[segmentId]
    queuedSegmentIds.delete(segmentId)
  }

  function setSegments(list: NarrationSegment[]) {
    const previousById = new Map(segments.value.map(segment => [segment.id, segment]))
    const ordered = sortSegments(list, 'position')
    const validIds = new Set(ordered.map(segment => segment.id))

    for (const segmentId of Object.keys(transcriptions).map(Number)) {
      if (!validIds.has(segmentId)) {
        clearSegmentTransientState(segmentId)
      }
    }

    for (const queuedId of [...queuedSegmentIds]) {
      if (!validIds.has(queuedId)) {
        queuedSegmentIds.delete(queuedId)
      }
    }

    for (const segment of ordered) {
      const previous = previousById.get(segment.id)
      if (!previous) continue

      if (segmentAudioChanged(previous, segment)) {
        audioVersion[segment.id] = (audioVersion[segment.id] || 0) + 1
        delete transcriptions[segment.id]
      }

      if (segment.status !== 'done') {
        delete transcriptions[segment.id]
      }
    }

    segments.value = ordered

    if (expandedTranscript.value !== null && !validIds.has(expandedTranscript.value)) {
      expandedTranscript.value = null
    }

    if (editingId.value !== null && !validIds.has(editingId.value)) {
      editingId.value = null
      editText.value = ''
    }
  }

  function updateSegmentInPlace(segment: NarrationSegment) {
    const index = segments.value.findIndex(item => item.id === segment.id)
    if (index < 0) return

    const previous = segments.value[index]
    const audioChanged = segmentAudioChanged(previous, segment)

    segments.value[index] = segment
    segments.value = sortSegments(segments.value, 'position')

    if (audioChanged) {
      audioVersion[segment.id] = (audioVersion[segment.id] || 0) + 1
      delete transcriptions[segment.id]
    }
  }

  async function fetchSegments() {
    const requestId = ++fetchSegmentsRequestId
    const activeProjectId = projectId.value

    loading.value = true
    error.value = null

    try {
      const data = await $fetch<NarrationSegment[]>(`${baseURL}/api/projects/${activeProjectId}/segments`)
      if (requestId !== fetchSegmentsRequestId || projectId.value !== activeProjectId) return
      setSegments(data)
    } catch (err: any) {
      if (requestId !== fetchSegmentsRequestId || projectId.value !== activeProjectId) return
      error.value = asErrorMessage(err, 'Failed to fetch narration segments')
    } finally {
      if (requestId === fetchSegmentsRequestId && projectId.value === activeProjectId) {
        loading.value = false
      }
    }
  }

  async function fetchProjectTranscriptions() {
    const activeProjectId = projectId.value

    try {
      const data = await $fetch<Record<string, NarrationTranscription>>(
        `${baseURL}/api/projects/${activeProjectId}/transcriptions`,
      )

      if (projectId.value !== activeProjectId) return

      for (const key of Object.keys(transcriptions)) {
        delete transcriptions[Number(key)]
      }

      const validIds = new Set(segments.value.map(segment => segment.id))
      for (const [segmentId, transcription] of Object.entries(data)) {
        const parsed = Number(segmentId)
        if (validIds.has(parsed)) {
          transcriptions[parsed] = transcription
        }
      }
    } catch {
      // Optional payload; keep UI interactive.
    }
  }

  async function refreshWorkspace() {
    await fetchSegments()
    await fetchProjectTranscriptions()
  }

  async function addSegment() {
    const text = addText.value.trim()
    if (!text) return

    try {
      await $fetch(`${baseURL}/api/projects/${projectId.value}/segments`, {
        method: 'POST',
        body: {
          text,
          service: addService.value,
        },
      })
      addText.value = ''
      showAdd.value = false
      await fetchSegments()
      status.value = 'Segment added'
    } catch (err: any) {
      status.value = asErrorMessage(err, 'Failed to add segment')
    }
  }

  async function importScript() {
    const text = importText.value.trim()
    if (!text) return

    try {
      await $fetch(`${baseURL}/api/projects/${projectId.value}/segments/import`, {
        method: 'POST',
        body: {
          text,
          service: importService.value,
        },
      })

      importText.value = ''
      showImport.value = false
      await refreshWorkspace()
      status.value = 'Script imported'
    } catch (err: any) {
      status.value = asErrorMessage(err, 'Script import failed')
    }
  }

  function startEdit(segment: NarrationSegment) {
    editingId.value = segment.id
    editText.value = segment.text
  }

  function cancelEdit() {
    editingId.value = null
    editText.value = ''
  }

  async function saveEdit(segmentId: number) {
    const text = editText.value.trim()
    if (!text) return

    try {
      const updated = await $fetch<NarrationSegment>(`${baseURL}/api/segments/${segmentId}`, {
        method: 'PUT',
        body: { text },
      })

      updateSegmentInPlace(updated)
      delete transcriptions[segmentId]
      cancelEdit()
      status.value = 'Segment updated'
    } catch (err: any) {
      status.value = asErrorMessage(err, 'Failed to save segment')
    }
  }

  async function updateSegmentService(segmentId: number, service: NarrationService) {
    try {
      const updated = await $fetch<NarrationSegment>(`${baseURL}/api/segments/${segmentId}`, {
        method: 'PUT',
        body: { service },
      })
      updateSegmentInPlace(updated)
    } catch (err: any) {
      status.value = asErrorMessage(err, 'Failed to update service')
    }
  }

  async function moveSegment(segmentId: number, direction: -1 | 1) {
    const ordered = sortSegments(segments.value, 'position')
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
      status.value = asErrorMessage(err, 'Failed to reorder segments')
    }
  }

  async function deleteSegment(segmentId: number) {
    try {
      await $fetch(`${baseURL}/api/segments/${segmentId}`, { method: 'DELETE' })
      clearSegmentTransientState(segmentId)
      if (expandedTranscript.value === segmentId) expandedTranscript.value = null
      await fetchSegments()
      status.value = 'Segment deleted'
    } catch (err: any) {
      status.value = asErrorMessage(err, 'Failed to delete segment')
    }
  }

  async function clearAllSegments() {
    try {
      await $fetch(`${baseURL}/api/projects/${projectId.value}/segments`, { method: 'DELETE' })

      segments.value = []
      for (const key of Object.keys(transcriptions)) delete transcriptions[Number(key)]
      for (const key of Object.keys(transcribing)) delete transcribing[Number(key)]
      for (const key of Object.keys(audioVersion)) delete audioVersion[Number(key)]
      for (const key of Object.keys(regenText)) delete regenText[Number(key)]

      queuedSegmentIds.clear()
      expandedTranscript.value = null
      cancelEdit()
      status.value = 'All segments cleared'
    } catch (err: any) {
      status.value = asErrorMessage(err, 'Failed to clear segments')
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
      status.value = asErrorMessage(err, 'Failed to update final flag')
    }
  }

  async function clearNeedsReview(segment: NarrationSegment) {
    if (!segment.needs_review) return

    try {
      await updateSegmentFlags(segment.id, { needs_review: false })
    } catch (err: any) {
      status.value = asErrorMessage(err, 'Failed to update review flag')
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
      status.value = asErrorMessage(err, 'Failed to mark segment done')
    }
  }

  async function generateOne(segmentId: number) {
    try {
      await $fetch(`${baseURL}/api/segments/${segmentId}/generate`, { method: 'POST' })
      queuedSegmentIds.add(segmentId)
      status.value = 'Segment queued for generation'
    } catch (err: any) {
      status.value = asErrorMessage(err, 'Generation request failed')
    }
  }

  async function regenerate(segmentId: number) {
    try {
      const text = regenText[segmentId]?.trim()
      await $fetch(`${baseURL}/api/segments/${segmentId}/regenerate`, {
        method: 'POST',
        body: text ? { text } : {},
      })

      queuedSegmentIds.add(segmentId)
      regenText[segmentId] = ''
      status.value = 'Regeneration queued'
    } catch (err: any) {
      status.value = asErrorMessage(err, 'Regeneration request failed')
    }
  }

  async function generateAll() {
    const pending = segments.value.filter(segment => segment.status !== 'done').map(segment => segment.id)
    if (!pending.length) return

    try {
      await $fetch(`${baseURL}/api/projects/${projectId.value}/generate/all`, { method: 'POST' })
      for (const id of pending) queuedSegmentIds.add(id)
      status.value = `Queued ${pending.length} segment${pending.length === 1 ? '' : 's'}`
    } catch (err: any) {
      status.value = asErrorMessage(err, 'Generate-all request failed')
    }
  }

  async function retryFailed() {
    const failures = segments.value.filter(segment => segment.status === 'error').map(segment => segment.id)
    if (!failures.length) return

    try {
      await $fetch(`${baseURL}/api/projects/${projectId.value}/generate/failed`, { method: 'POST' })
      for (const id of failures) queuedSegmentIds.add(id)
      status.value = `Queued ${failures.length} failed segment${failures.length === 1 ? '' : 's'}`
    } catch (err: any) {
      status.value = asErrorMessage(err, 'Retry request failed')
    }
  }

  async function cancelGeneration() {
    cancelling.value = true

    try {
      await $fetch(`${baseURL}/api/generation/cancel`, { method: 'POST' })
      ws?.send(JSON.stringify({ type: 'cancel' }))
    } catch (err: any) {
      status.value = asErrorMessage(err, 'Cancel request failed')
    } finally {
      setTimeout(() => {
        cancelling.value = false
      }, 400)
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
      return true
    } catch (err: any) {
      if (!options.silent) {
        status.value = asErrorMessage(err, 'Transcription failed')
      }
      return false
    } finally {
      delete transcribing[segmentId]
    }
  }

  async function deleteTranscription(segmentId: number) {
    try {
      await $fetch(`${baseURL}/api/segments/${segmentId}/transcription`, { method: 'DELETE' })
      delete transcriptions[segmentId]
      if (expandedTranscript.value === segmentId) {
        expandedTranscript.value = null
      }
    } catch (err: any) {
      status.value = asErrorMessage(err, 'Failed to delete transcription')
    }
  }

  async function transcribeAll() {
    const queue = segments.value.filter(segment => (
      segment.status === 'done'
      && !!segment.audio_path
      && !transcriptions[segment.id]
    ))

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

  function exportAudio() {
    const params = new URLSearchParams({
      format: exportFormat.value,
      gap_ms: String(exportGapMs.value),
      fade_ms: String(exportFadeMs.value),
      normalize: String(exportNormalize.value),
    })

    if (import.meta.client) {
      window.location.href = `${baseURL}/api/projects/${projectId.value}/export?${params.toString()}`
    }
  }

  function exportAudioZip() {
    if (import.meta.client) {
      window.location.href = `${baseURL}/api/projects/${projectId.value}/export-zip`
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

      await refreshWorkspace()

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

      await refreshWorkspace()
      return
    }

    if (message.type === 'queue_status' && !message.active_job_id && !message.queue_length) {
      generating.value = false
      cancelling.value = false
      queuedSegmentIds.clear()
    }
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

      void handleWsMessage(message)
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

  function resetWorkspaceState() {
    fetchSegmentsRequestId += 1

    segments.value = []
    for (const key of Object.keys(transcriptions)) delete transcriptions[Number(key)]
    for (const key of Object.keys(transcribing)) delete transcribing[Number(key)]
    for (const key of Object.keys(audioVersion)) delete audioVersion[Number(key)]
    for (const key of Object.keys(regenText)) delete regenText[Number(key)]

    queuedSegmentIds.clear()

    cancelEdit()
    expandedTranscript.value = null

    importText.value = ''
    addText.value = ''
    showImport.value = false
    showAdd.value = false
    showTimeline.value = false
    showExport.value = false
    exportFormat.value = 'wav'
    exportGapMs.value = 750
    exportFadeMs.value = 50
    exportNormalize.value = true

    loading.value = false
    error.value = null
    status.value = ''

    generating.value = false
    cancelling.value = false
    genIndex.value = 0
    genTotal.value = 0
    genEstimate.value = null

    segmentStatusFilter.value = 'all'
    segmentSortMode.value = 'position'
    showFinalSegments.value = true
    showNeedsReviewOnly.value = false

    transcribeAllProgress.value = null
  }

  watch(
    () => projectId.value,
    async () => {
      resetWorkspaceState()

      if (!projectId.value) return

      await refreshWorkspace()
    },
    { immediate: true },
  )

  onMounted(() => {
    connectWs()
  })

  onUnmounted(() => {
    if (wsReconnectTimer) clearTimeout(wsReconnectTimer)
    if (ws) ws.close()
  })

  return {
    loading,
    error,
    status,

    segments,
    transcriptions,
    transcribing,
    audioVersion,
    queuedSegmentIds,

    editingId,
    editText,
    expandedTranscript,
    regenText,

    showImport,
    showAdd,
    showTimeline,
    showExport,

    importText,
    importService,
    addText,
    addService,

    exportFormat,
    exportGapMs,
    exportFadeMs,
    exportNormalize,

    generating,
    cancelling,
    genIndex,
    genTotal,
    genEstimate,

    segmentStatusFilter,
    segmentSortMode,
    showFinalSegments,
    showNeedsReviewOnly,
    transcribeAllProgress,

    pendingCount,
    queuedCount,
    generatingCount,
    doneCount,
    errorCount,

    filteredSegments,
    hasAudio,
    genProgress,
    totalDuration,

    segmentAudioUrl,
    segmentCleanedAudioUrl,
    segmentPreferredAudioUrl,

    fetchSegments,
    fetchProjectTranscriptions,
    refreshWorkspace,

    addSegment,
    importScript,

    startEdit,
    cancelEdit,
    saveEdit,
    updateSegmentService,
    moveSegment,
    deleteSegment,
    clearAllSegments,

    toggleFinal,
    clearNeedsReview,
    markSegmentDone,

    generateOne,
    regenerate,
    generateAll,
    retryFailed,
    cancelGeneration,

    transcribeSegment,
    deleteTranscription,
    transcribeAll,
    toggleTranscript,

    exportAudio,
    exportAudioZip,

    resolveSegmentDisplayStatus,
  }
}
