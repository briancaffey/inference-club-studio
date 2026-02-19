<script setup lang="ts">
import {
  AlertCircle,
  CheckCircle2,
  Loader2,
  Mic2,
  Plus,
  RefreshCw,
  Upload,
  Waves,
  XCircle,
} from 'lucide-vue-next'
import type {
  NarrationSegment,
  NarrationService,
  NarrationTranscription,
  NarrationVariant,
  NarrationVoiceSample,
} from '~/types'

interface ArticleChunk {
  raw: string
  segments: string[]
  processed: boolean
  error: boolean
  retrying: boolean
}

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

const editingId = ref<number | null>(null)
const editText = ref('')
const expandedVariants = ref<number | null>(null)
const expandedTranscript = ref<number | null>(null)
const regenText = reactive<Record<number, string>>({})
const confirmClear = ref(false)

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

const showScriptEditor = ref(false)
const scriptText = ref('')
const scriptSyncing = ref(false)
const scriptSyncStatus = ref('')

const showVoices = ref(false)
const voiceSamples = ref<NarrationVoiceSample[]>([])
const magpieVoices = ref<string[]>([])
const voiceName = ref('')
const voiceTranscript = ref('')
const voiceFile = ref<File | null>(null)
const globalVoiceSampleId = ref<number | null>(null)
const globalMagpieVoice = ref('')

const showExport = ref(false)
const exportFormat = ref<'wav' | 'mp3'>('wav')
const exportGapMs = ref(750)
const exportFadeMs = ref(50)
const exportNormalize = ref(true)

const generating = ref(false)
const cancelling = ref(false)
const genIndex = ref(0)
const genTotal = ref(0)
const genEstimate = ref<number | null>(null)

let ws: WebSocket | null = null
let wsReconnectTimer: ReturnType<typeof setTimeout> | null = null

const pendingCount = computed(() => segments.value.filter(segment => segment.status !== 'done').length)
const doneCount = computed(() => segments.value.filter(segment => segment.status === 'done').length)
const errorCount = computed(() => segments.value.filter(segment => segment.status === 'error').length)
const hasAudio = computed(() => doneCount.value > 0)
const genProgress = computed(() => {
  if (!genTotal.value) return 0
  return Math.round((genIndex.value / genTotal.value) * 100)
})
const totalDuration = computed(() => {
  const total = segments.value.reduce((sum, segment) => sum + (segment.duration_seconds || 0), 0)
  return formatDuration(total)
})

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

function statusClass(segmentStatus: string) {
  if (segmentStatus === 'done') return 'bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-300'
  if (segmentStatus === 'generating') return 'bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-300'
  if (segmentStatus === 'error') return 'bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300'
  return 'bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300'
}

function sortSegments(list: NarrationSegment[]) {
  return [...list].sort((a, b) => a.position - b.position)
}

function setSegments(list: NarrationSegment[]) {
  segments.value = sortSegments(list)
  if (showScriptEditor.value) {
    scriptText.value = segments.value.map(segment => segment.text).join('\n')
  }
}

function updateSegmentInPlace(segment: NarrationSegment) {
  const index = segments.value.findIndex(item => item.id === segment.id)
  if (index !== -1) {
    segments.value[index] = segment
    segments.value = sortSegments(segments.value)
  }
}

function segmentAudioUrl(segmentId: number) {
  return `${baseURL}/api/segments/${segmentId}/audio?v=${audioVersion[segmentId] || 0}`
}

function variantAudioUrl(variantId: number) {
  return `${baseURL}/api/variants/${variantId}/audio`
}

function voiceSampleAudioUrl(sampleId: number) {
  return `${baseURL}/api/voice-samples/${sampleId}/audio`
}

async function fetchSegments() {
  loading.value = true
  error.value = null
  try {
    const data = await $fetch<NarrationSegment[]>(`${baseURL}/api/projects/${props.projectId}/segments`)
    setSegments(data)
  } catch (err: any) {
    error.value = err?.data?.detail || err?.message || 'Failed to fetch narration segments'
  } finally {
    loading.value = false
  }
}

async function fetchVariants(segmentId: number) {
  const data = await $fetch<NarrationVariant[]>(`${baseURL}/api/segments/${segmentId}/variants`)
  variantsMap[segmentId] = data
}

async function fetchVoiceSamples() {
  const data = await $fetch<NarrationVoiceSample[]>(`${baseURL}/api/voice-samples`)
  voiceSamples.value = data
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
  const data = await $fetch<Record<string, NarrationTranscription>>(
    `${baseURL}/api/projects/${props.projectId}/transcriptions`,
  )

  for (const key of Object.keys(transcriptions)) {
    delete transcriptions[Number(key)]
  }

  for (const [segmentId, transcription] of Object.entries(data)) {
    transcriptions[Number(segmentId)] = transcription
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
    editingId.value = null
    editText.value = ''
  } catch (err: any) {
    status.value = err?.data?.detail || 'Failed to save segment'
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
  if (!chunk) return
  if (chunk.segments.length <= 1) return
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
    regenText[segmentId] = ''
  } catch (err: any) {
    status.value = err?.data?.detail || 'Regeneration request failed'
  }
}

async function generateAll() {
  const pending = segments.value.filter(segment => segment.status !== 'done').map(segment => segment.id)
  if (!pending.length) return

  try {
    await patchGlobalVoice(pending)
    await $fetch(`${baseURL}/api/projects/${props.projectId}/generate/all`, { method: 'POST' })
  } catch (err: any) {
    status.value = err?.data?.detail || 'Generate-all request failed'
  }
}

async function retryFailed() {
  const failures = segments.value.filter(segment => segment.status === 'error').map(segment => segment.id)
  if (!failures.length) return

  try {
    await patchGlobalVoice(failures)
    await $fetch(`${baseURL}/api/projects/${props.projectId}/generate/failed`, { method: 'POST' })
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
    audioVersion[segmentId] = (audioVersion[segmentId] || 0) + 1
    await fetchVariants(segmentId)
  } catch (err: any) {
    status.value = err?.data?.detail || 'Failed to select variant'
  }
}

async function deleteVariant(variant: NarrationVariant) {
  if (!confirm('Delete this variant?')) return

  try {
    await $fetch(`${baseURL}/api/variants/${variant.id}`, { method: 'DELETE' })
    audioVersion[variant.segment_id] = (audioVersion[variant.segment_id] || 0) + 1
    await fetchVariants(variant.segment_id)
    await fetchSegments()
  } catch (err: any) {
    status.value = err?.data?.detail || 'Failed to delete variant'
  }
}

async function uploadVoiceSample() {
  if (!voiceName.value.trim() || !voiceFile.value) return

  const formData = new FormData()
  formData.append('name', voiceName.value.trim())
  formData.append('transcript', voiceTranscript.value.trim())
  formData.append('audio', voiceFile.value)

  try {
    await $fetch(`${baseURL}/api/voice-samples`, {
      method: 'POST',
      body: formData,
    })
    voiceName.value = ''
    voiceTranscript.value = ''
    voiceFile.value = null
    await fetchVoiceSamples()
  } catch (err: any) {
    status.value = err?.data?.detail || 'Failed to upload voice sample'
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

function onVoiceFileChange(event: Event) {
  const target = event.target as HTMLInputElement
  voiceFile.value = target.files?.[0] || null
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

async function transcribeSegment(segmentId: number) {
  if (transcribing[segmentId]) return

  transcribing[segmentId] = true
  try {
    const transcription = await $fetch<NarrationTranscription>(`${baseURL}/api/segments/${segmentId}/transcribe`, {
      method: 'POST',
    })
    transcriptions[segmentId] = transcription
  } catch (err: any) {
    status.value = err?.data?.detail || 'Transcription failed'
  } finally {
    delete transcribing[segmentId]
  }
}

async function transcribeAll() {
  const candidates = segments.value.filter(segment => segment.status === 'done' && segment.audio_path)
  if (!candidates.length) return

  status.value = `Transcribing ${candidates.length} segments...`
  for (const segment of candidates) {
    if (transcriptions[segment.id]) continue
    await transcribeSegment(segment.id)
  }
  status.value = 'Transcription pass complete'
}

async function deleteTranscription(segmentId: number) {
  try {
    await $fetch(`${baseURL}/api/segments/${segmentId}/transcription`, { method: 'DELETE' })
    delete transcriptions[segmentId]
  } catch (err: any) {
    status.value = err?.data?.detail || 'Failed to delete transcription'
  }
}

function connectWs() {
  if (!wsUrl.value) return

  if (ws) {
    ws.close()
    ws = null
  }

  ws = new WebSocket(wsUrl.value)

  ws.onmessage = async (event) => {
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

async function handleWsMessage(message: any) {
  if (message.type === 'queued') {
    const queuedIds: number[] = message.segment_ids || []
    if (!queuedIds.some(id => isRelevantSegment(id))) return

    generating.value = true
    genTotal.value = queuedIds.length
    genIndex.value = 0
    status.value = `Queued ${queuedIds.length} segment${queuedIds.length === 1 ? '' : 's'}...`
    return
  }

  if (message.type === 'segment_start') {
    if (!isRelevantSegment(message.segment_id)) return

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

    genIndex.value = (message.index || 0) + 1
    if (message.segment) {
      updateSegmentInPlace(message.segment as NarrationSegment)
    }
    audioVersion[message.segment_id] = (audioVersion[message.segment_id] || 0) + 1
    status.value = `Segment ${message.index + 1}/${message.total} complete`
    return
  }

  if (message.type === 'segment_error') {
    if (!isRelevantSegment(message.segment_id)) return

    genIndex.value = (message.index || 0) + 1
    const index = segments.value.findIndex(segment => segment.id === message.segment_id)
    if (index !== -1) {
      segments.value[index] = {
        ...segments.value[index],
        status: 'error',
        error_message: message.error || 'Generation failed',
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
    return
  }

  if (message.type === 'queue_status' && !message.active_job_id) {
    generating.value = false
    cancelling.value = false
  }
}

function resetWorkspaceState() {
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
  editingId.value = null
  editText.value = ''
  expandedVariants.value = null
  expandedTranscript.value = null
  status.value = ''
  error.value = null
}

watch(
  () => props.projectId,
  async () => {
    resetWorkspaceState()
    await fetchSegments()
    await fetchVoiceSamples()
    await fetchProjectTranscriptions()
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
          <Button size="sm" variant="outline" :disabled="!hasAudio" @click="transcribeAll">
            Transcribe All
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
            <div class="mb-1 flex items-center justify-between gap-2">
              <div>
                <p class="text-sm font-medium">{{ sample.name }}</p>
                <p class="text-xs text-muted-foreground">{{ sample.transcript || 'No transcript' }}</p>
              </div>
              <Button size="sm" variant="ghost" class="text-red-600" @click="deleteVoiceSample(sample.id)">
                Delete
              </Button>
            </div>
            <audio :src="voiceSampleAudioUrl(sample.id)" controls preload="none" class="w-full" />
          </div>
        </div>

        <div class="grid gap-2 border-t pt-3 sm:grid-cols-2">
          <Input v-model="voiceName" placeholder="Voice name" />
          <Input v-model="voiceTranscript" placeholder="Transcript" />
          <input type="file" accept=".wav" class="text-sm" @change="onVoiceFileChange">
          <Button size="sm" :disabled="!voiceName.trim() || !voiceFile" @click="uploadVoiceSample">
            Upload Sample
          </Button>
        </div>
      </CardContent>
    </Card>

    <Card v-if="showExport">
      <CardHeader class="pb-3">
        <CardTitle class="text-base">Export</CardTitle>
      </CardHeader>
      <CardContent class="grid gap-3 sm:grid-cols-4">
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
            Download
          </Button>
        </div>
      </CardContent>
    </Card>

    <div v-if="loading" class="flex items-center justify-center py-8 text-sm text-muted-foreground">
      <Loader2 class="mr-2 h-4 w-4 animate-spin" />
      Loading narration segments...
    </div>

    <div v-else-if="!segments.length" class="rounded-md border border-dashed p-8 text-center text-sm text-muted-foreground">
      No narration segments yet. Import a script or add one manually.
    </div>

    <div v-else class="space-y-3">
      <Card v-for="segment in segments" :key="segment.id">
        <CardHeader class="pb-3">
          <div class="flex flex-wrap items-start justify-between gap-2">
            <div class="space-y-1">
              <div class="flex items-center gap-2">
                <Badge variant="outline">#{{ segment.position }}</Badge>
                <span class="rounded px-2 py-0.5 text-xs font-medium" :class="statusClass(segment.status)">
                  {{ segment.status }}
                </span>
              </div>
              <div v-if="segment.error_message" class="flex items-center gap-1 text-xs text-red-600 dark:text-red-400">
                <XCircle class="h-3 w-3" />
                {{ segment.error_message }}
              </div>
            </div>

            <div class="flex items-center gap-2">
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
            </div>
          </div>
        </CardHeader>

        <CardContent class="space-y-3">
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
            <Button size="sm" variant="outline" class="text-red-600" @click="deleteSegment(segment.id)">
              Delete
            </Button>
            <Button size="sm" @click="generateOne(segment.id)">
              Generate
            </Button>
            <Button size="sm" variant="outline" @click="regenerate(segment.id)">
              Regenerate
            </Button>
            <Button size="sm" variant="outline" @click="toggleVariants(segment.id)">
              Variants
            </Button>
            <Button size="sm" variant="outline" :disabled="!segment.audio_path || !!transcribing[segment.id]" @click="transcribeSegment(segment.id)">
              {{ transcribing[segment.id] ? 'Transcribing...' : 'Transcribe' }}
            </Button>
            <Button
              v-if="transcriptions[segment.id]"
              size="sm"
              variant="outline"
              @click="expandedTranscript = expandedTranscript === segment.id ? null : segment.id"
            >
              Transcript
            </Button>
          </div>

          <Input
            v-model="regenText[segment.id]"
            placeholder="Optional regenerate text override"
          />

          <audio
            v-if="segment.status === 'done' && segment.audio_path"
            :src="segmentAudioUrl(segment.id)"
            controls
            preload="none"
            class="w-full"
          />

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
                  <span>#{{ variant.id }} · {{ variant.service }}</span>
                  <div class="flex items-center gap-2">
                    <Button size="sm" variant="outline" class="h-7 px-2" @click="selectVariant(segment.id, variant.id)">
                      Select
                    </Button>
                    <Button size="sm" variant="ghost" class="h-7 px-2 text-red-600" @click="deleteVariant(variant)">
                      Delete
                    </Button>
                  </div>
                </div>
                <audio :src="variantAudioUrl(variant.id)" controls preload="none" class="w-full" />
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
              <span
                v-for="(word, index) in transcriptions[segment.id].words"
                :key="`${segment.id}-word-${index}`"
                class="rounded bg-background px-1.5 py-0.5 text-xs"
              >
                {{ word.word }}
              </span>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  </div>
</template>
