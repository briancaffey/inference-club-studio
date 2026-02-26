import {
  computed,
  nextTick,
  onUnmounted,
  ref,
  watch,
  type Ref,
} from 'vue'
import type {
  NarrationSegment,
  NarrationTranscription,
} from '~/types'
import { useApi } from '~/composables/useApi'

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

interface UseNarrationTrimNextOptions {
  segments: Ref<NarrationSegment[]>
  transcriptions: Record<number, NarrationTranscription>
  audioVersion: Record<number, number>
  playbackSpeed: Ref<number>
  status: Ref<string>
  refreshWorkspace: () => Promise<void>
  ensureTranscription?: (segmentId: number) => Promise<void>
}

const MIN_TRIM_GAP_MS = 50

export function useNarrationTrimNext(options: UseNarrationTrimNextOptions) {
  const { baseURL } = useApi()

  const expandedTrimSegmentId = ref<number | null>(null)
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

  let trimWaveformRequestId = 0
  let audioContext: AudioContext | null = null
  let trimPreviewSource: AudioBufferSourceNode | null = null

  const trimSelectionStart = computed(() => Math.min(trimStart.value, trimEnd.value))
  const trimSelectionEnd = computed(() => Math.max(trimStart.value, trimEnd.value))
  const trimSelectionDuration = computed(() => Math.max(0, trimSelectionEnd.value - trimSelectionStart.value))
  const hasTrimSelection = computed(() => trimSelectionDuration.value >= MIN_TRIM_GAP_MS)
  const trimRangeLabel = computed(() => {
    if (!hasTrimSelection.value) {
      return `Select deadspace to remove (${Math.round(trimAudioDuration.value)}ms clip)`
    }

    const startSeconds = (trimSelectionStart.value / 1000).toFixed(2)
    const endSeconds = (trimSelectionEnd.value / 1000).toFixed(2)
    const durationSeconds = (trimSelectionDuration.value / 1000).toFixed(2)
    return `Remove ${startSeconds}s - ${endSeconds}s (${durationSeconds}s)`
  })

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

  function segmentHasTrimmableAudio(segment: NarrationSegment) {
    if (!segment.audio_path) return false
    return segment.status === 'done' || segment.status === 'error'
  }

  function segmentNeedsTrim(segment: NarrationSegment) {
    if (!segmentHasTrimmableAudio(segment)) return false

    const transcription = options.transcriptions[segment.id]
    if (!transcription?.words?.length || !segment.duration_seconds) return false

    const firstWordStart = transcription.words[0]?.start || 0
    const lastWordEnd = transcription.words[transcription.words.length - 1]?.end || 0

    return firstWordStart > 0.3 || (segment.duration_seconds - lastWordEnd) > 0.5
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

  async function decodeSegmentAudio(segmentId: number, expectedVersion: number) {
    if (!import.meta.client) return null

    const context = getAudioContext()
    if (!context) return null

    const response = await fetch(`${baseURL}/api/segments/${segmentId}/audio?v=${expectedVersion}`)
    if (!response.ok) {
      throw new Error(`Audio fetch failed (${response.status})`)
    }

    const bytes = await response.arrayBuffer()
    if ((options.audioVersion[segmentId] || 0) !== expectedVersion) return null
    return context.decodeAudioData(bytes.slice(0))
  }

  async function fetchSegmentWaveform(segmentId: number, points: number) {
    return await $fetch<SegmentWaveformResponse>(`${baseURL}/api/segments/${segmentId}/waveform`, {
      query: {
        points,
        source: 'original',
      },
    })
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

    for (let i = 0; i < samples.length; i += 1) {
      const ms = (i / samples.length) * totalMs
      const inRemovedRange = hasTrimSelection.value && ms >= removeStartMs && ms <= removeEndMs
      const barHeight = Math.max(1, samples[i] * (height * 0.78))

      context.fillStyle = inRemovedRange
        ? (isDark ? 'rgba(248,113,113,0.74)' : 'rgba(239,68,68,0.64)')
        : (isDark ? 'rgba(56,189,248,0.36)' : 'rgba(14,165,233,0.3)')

      context.fillRect(i * gap, midY - (barHeight / 2), barWidth, barHeight)
    }

    const transcription = options.transcriptions[segmentId]
    if (!transcription?.words?.length) return

    context.font = '9px ui-sans-serif, system-ui, -apple-system, Segoe UI'
    context.textAlign = 'left'

    for (const word of transcription.words) {
      const startMs = Math.max(0, Math.min(totalMs, word.start * 1000))
      const endMs = Math.max(startMs, Math.min(totalMs, word.end * 1000))
      const x = Math.max(0, Math.min(width - 1, (startMs / totalMs) * width))
      const inRemovedRange = hasTrimSelection.value && startMs >= removeStartMs && endMs <= removeEndMs

      context.fillStyle = inRemovedRange
        ? (isDark ? 'rgba(248,113,113,0.85)' : 'rgba(220,38,38,0.72)')
        : (isDark ? 'rgba(125,211,252,0.56)' : 'rgba(3,105,161,0.48)')

      context.fillRect(x, height - 14, 1, 14)

      context.fillStyle = inRemovedRange
        ? (isDark ? 'rgba(254,202,202,0.95)' : 'rgba(127,29,29,0.86)')
        : (isDark ? 'rgba(186,230,253,0.95)' : 'rgba(8,47,73,0.78)')
      context.fillText(word.word, Math.min(width - 2, x + 2), height - 3)
    }
  }

  async function loadTrimWaveform(segmentId: number) {
    const segment = options.segments.value.find(item => item.id === segmentId)
    if (!segment || !segmentHasTrimmableAudio(segment)) return

    const requestId = ++trimWaveformRequestId
    trimWaveformLoading.value = true
    trimWaveformError.value = ''

    try {
      let decoded: AudioBuffer | null = null
      let lastError: unknown = null

      for (let attempt = 0; attempt < 3; attempt += 1) {
        if (requestId !== trimWaveformRequestId || expandedTrimSegmentId.value !== segmentId) {
          return
        }

        const expectedVersion = options.audioVersion[segmentId] || 0
        try {
          decoded = await decodeSegmentAudio(segmentId, expectedVersion)
        } catch (err) {
          lastError = err
        }

        if (decoded) break
        await new Promise(resolve => setTimeout(resolve, 120))
      }

      if (requestId !== trimWaveformRequestId || expandedTrimSegmentId.value !== segmentId) {
        return
      }

      if (!decoded) {
        try {
          const serverWaveform = await fetchSegmentWaveform(segmentId, 520)
          if (requestId !== trimWaveformRequestId || expandedTrimSegmentId.value !== segmentId) {
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
    const segment = options.segments.value.find(item => item.id === segmentId)
    if (!segment || !segmentHasTrimmableAudio(segment)) return

    const requestId = ++trimWaveformRequestId
    trimWaveformLoading.value = true
    trimWaveformError.value = ''

    try {
      const serverWaveform = await fetchSegmentWaveform(segmentId, 520)
      if (requestId !== trimWaveformRequestId || expandedTrimSegmentId.value !== segmentId) return

      trimSegmentId.value = segmentId
      trimDecodedBuffer.value = null
      trimAudioDuration.value = Math.max(1, Math.round(serverWaveform.duration_ms))
      trimWaveformData.value = Float32Array.from(serverWaveform.samples)
      resetTrimSelectionState()

      await nextTick()
      drawTrimWaveform(segmentId)
      options.status.value = 'Waveform regenerated from source audio'
    } catch (err: any) {
      trimWaveformError.value = err?.data?.detail || 'Could not regenerate waveform'
    } finally {
      if (requestId === trimWaveformRequestId) {
        trimWaveformLoading.value = false
      }
    }
  }

  function beginTrimSelection() {
    if (!trimWaveformData.value || trimWaveformLoading.value) return
    resetTrimSelectionState()
    trimSelectionArmed.value = true
  }

  function clearTrimSelection() {
    const segmentId = expandedTrimSegmentId.value
    resetTrimSelectionState()
    if (segmentId !== null) {
      drawTrimWaveform(segmentId)
    }
  }

  function cancelTrimDeadspace() {
    if (expandedTrimSegmentId.value === null) {
      resetTrimWaveformState()
      return
    }
    expandedTrimSegmentId.value = null
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
        options.status.value = 'Selection is too short. Drag a wider deadspace section.'
      }

      drawTrimWaveform(segmentId)
      document.removeEventListener('pointermove', onMove)
      document.removeEventListener('pointerup', onUp)
    }

    document.addEventListener('pointermove', onMove)
    document.addEventListener('pointerup', onUp)
  }

  async function previewTrim() {
    const segmentId = expandedTrimSegmentId.value
    if (!segmentId || trimSegmentId.value !== segmentId) return
    if (!hasTrimSelection.value) {
      options.status.value = 'Select deadspace to preview'
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
      options.status.value = 'Selected deadspace is not valid for preview'
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
    source.playbackRate.value = options.playbackSpeed.value
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
    const segmentId = expandedTrimSegmentId.value
    if (!segmentId) return

    const segment = options.segments.value.find(item => item.id === segmentId)
    if (!segment) return

    if (!hasTrimSelection.value) {
      options.status.value = 'Select deadspace to remove'
      return
    }

    if (trimAudioDuration.value - trimSelectionDuration.value < MIN_TRIM_GAP_MS) {
      options.status.value = 'Selected deadspace is too large to remove'
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

      if (payload.transcription) {
        options.transcriptions[segment.id] = payload.transcription
      } else {
        delete options.transcriptions[segment.id]
      }

      await options.refreshWorkspace()
      await loadTrimWaveform(segment.id)

      options.status.value = 'Deadspace removed and saved'
    } catch (err: any) {
      options.status.value = err?.data?.detail || err?.message || 'Trim failed'
    } finally {
      trimApplying.value = false
    }
  }

  async function toggleTrim(segmentId: number) {
    if (expandedTrimSegmentId.value === segmentId) {
      cancelTrimDeadspace()
      return
    }

    expandedTrimSegmentId.value = segmentId
    stopTrimPreview()
    resetTrimSelectionState()
    trimWaveformError.value = ''

    if (!options.transcriptions[segmentId] && options.ensureTranscription) {
      await options.ensureTranscription(segmentId)
    }
  }

  watch(
    () => expandedTrimSegmentId.value,
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
    () => options.transcriptions,
    () => {
      if (expandedTrimSegmentId.value !== null) {
        nextTick(() => drawTrimWaveform(expandedTrimSegmentId.value as number))
      }
    },
    { deep: true },
  )

  onUnmounted(() => {
    resetTrimWaveformState()

    if (audioContext) {
      audioContext.close().catch(() => {})
      audioContext = null
    }
  })

  return {
    expandedTrimSegmentId,
    trimStart,
    trimEnd,
    trimSelectionStart,
    trimSelectionEnd,
    trimSelectionDuration,
    hasTrimSelection,
    trimRangeLabel,
    trimWaveformData,
    trimAudioDuration,
    trimApplying,
    trimSelectionArmed,
    trimSelecting,
    trimSegmentId,
    trimDecodedBuffer,
    trimWaveformLoading,
    trimWaveformError,

    segmentHasTrimmableAudio,
    segmentNeedsTrim,

    toggleTrim,
    beginTrimSelection,
    clearTrimSelection,
    cancelTrimDeadspace,
    onTrimWaveformPointerDown,
    previewTrim,
    applyTrim,
    loadTrimWaveform,
    regenerateTrimWaveform,
    drawTrimWaveform,
  }
}
