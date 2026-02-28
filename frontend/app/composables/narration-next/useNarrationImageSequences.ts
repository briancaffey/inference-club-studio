import {
  onUnmounted,
  reactive,
  watch,
  type Ref,
} from 'vue'
import type {
  NarrationImageFrame,
  NarrationImageGenerationMode,
  NarrationImagePromptSuggestionResponse,
  NarrationImageSeries,
} from '~/types'
import { useApi } from '~/composables/useApi'

function asErrorMessage(err: any, fallback: string) {
  return err?.data?.detail || err?.message || fallback
}

interface FetchSeriesOptions {
  silent?: boolean
  throwOnError?: boolean
}

export interface NarrationImageManualSeriesInput {
  name?: string
  initialPrompt: string
  autoGenerate?: boolean
}

export interface NarrationImageAutoSeriesInput {
  name?: string
  creativeDirection: string
  targetImages?: number
}

export interface NarrationImageAddFrameInput {
  prompt: string
  parentFrameId?: string | null
  isFork?: boolean
  mode?: NarrationImageGenerationMode
}

export interface NarrationImageSuggestInput {
  sourceFrameId?: string | null
  guidance?: string
  count?: number
}

export interface NarrationImageRegenerateFrameInput {
  includeDescendants?: boolean
  autoGenerate?: boolean
}

export interface NarrationImageSequencesController {
  mediaUrl: (path: string | null) => string | null
  isPanelOpen: (segmentId: number) => boolean
  openPanel: (segmentId: number) => Promise<void>
  closePanel: (segmentId: number) => void
  togglePanel: (segmentId: number) => Promise<void>
  ensureSegmentLoaded: (segmentId: number) => Promise<void>
  clearSegment: (segmentId: number) => void
  clearAll: () => void
  listForSegment: (segmentId: number) => NarrationImageSeries[]
  latestPreviewFrames: (segmentId: number) => NarrationImageFrame[]
  isLoadingSegment: (segmentId: number) => boolean
  segmentError: (segmentId: number) => string | null
  isCreatingSegment: (segmentId: number) => boolean
  isSeriesBusy: (seriesId: string) => boolean
  isSeriesSuggesting: (seriesId: string) => boolean
  refreshSegment: (segmentId: number) => Promise<void>
  createManualSeries: (
    segmentId: number,
    input: NarrationImageManualSeriesInput,
  ) => Promise<NarrationImageSeries>
  createAutoSeries: (
    segmentId: number,
    input: NarrationImageAutoSeriesInput,
  ) => Promise<NarrationImageSeries>
  queueSeries: (segmentId: number, seriesId: string) => Promise<NarrationImageSeries>
  deleteSeries: (segmentId: number, seriesId: string) => Promise<void>
  addFrame: (
    segmentId: number,
    seriesId: string,
    input: NarrationImageAddFrameInput,
  ) => Promise<void>
  regenerateFrame: (
    segmentId: number,
    seriesId: string,
    frameId: string,
    input?: NarrationImageRegenerateFrameInput,
  ) => Promise<NarrationImageSeries>
  suggestPrompts: (
    seriesId: string,
    input?: NarrationImageSuggestInput,
  ) => Promise<string[]>
}

function sortByCreatedAtDesc(items: NarrationImageSeries[]) {
  return [...items].sort((a, b) => (
    Date.parse(b.created_at) - Date.parse(a.created_at)
  ))
}

function toTimestamp(value: string | null | undefined): number {
  if (!value) return 0
  const parsed = Date.parse(value)
  return Number.isNaN(parsed) ? 0 : parsed
}

export function useNarrationImageSequences(
  projectId: Ref<string>,
): NarrationImageSequencesController {
  const { baseURL, mediaUrl } = useApi()

  const panelOpenBySegment = reactive<Record<number, boolean>>({})
  const seriesBySegment = reactive<Record<number, NarrationImageSeries[]>>({})
  const loadingBySegment = reactive<Record<number, boolean>>({})
  const errorBySegment = reactive<Record<number, string | null>>({})
  const creatingBySegment = reactive<Record<number, boolean>>({})
  const busyBySeries = reactive<Record<string, boolean>>({})
  const suggestingBySeries = reactive<Record<string, boolean>>({})

  let pollInterval: ReturnType<typeof setInterval> | null = null
  let pollInFlight = false

  function loadedSegmentIds() {
    return Object.keys(seriesBySegment).map(Number)
  }

  function listForSegment(segmentId: number) {
    return seriesBySegment[segmentId] || []
  }

  function isPanelOpen(segmentId: number) {
    return !!panelOpenBySegment[segmentId]
  }

  function isLoadingSegment(segmentId: number) {
    return !!loadingBySegment[segmentId]
  }

  function segmentError(segmentId: number) {
    return errorBySegment[segmentId] || null
  }

  function isCreatingSegment(segmentId: number) {
    return !!creatingBySegment[segmentId]
  }

  function isSeriesBusy(seriesId: string) {
    return !!busyBySeries[seriesId]
  }

  function isSeriesSuggesting(seriesId: string) {
    return !!suggestingBySeries[seriesId]
  }

  function activeSegmentIds() {
    return loadedSegmentIds().filter(segmentId => (
      listForSegment(segmentId).some(series => (
        series.status === 'queued' || series.status === 'generating'
      ))
    ))
  }

  function latestPreviewFrames(segmentId: number): NarrationImageFrame[] {
    const candidates = listForSegment(segmentId)
      .map(series => {
        const completedFrames = [...series.frames]
          .filter(frame => (
            frame.status === 'completed'
            && !!frame.output_image_path
          ))
          .sort((a, b) => a.step_order - b.step_order)
        const latestFrame = completedFrames[completedFrames.length - 1]
        const score = Math.max(
          toTimestamp(series.completed_at),
          toTimestamp(latestFrame?.updated_at),
          toTimestamp(series.updated_at),
          toTimestamp(series.created_at),
        )
        return { completedFrames, score }
      })
      .filter(item => item.completedFrames.length > 0)
      .sort((a, b) => b.score - a.score)

    return candidates[0]?.completedFrames || []
  }

  function replaceSeriesList(segmentId: number, rows: NarrationImageSeries[]) {
    seriesBySegment[segmentId] = sortByCreatedAtDesc(rows)
  }

  function upsertSeries(segmentId: number, row: NarrationImageSeries) {
    const current = listForSegment(segmentId)
    const index = current.findIndex(item => item.id === row.id)
    if (index === -1) {
      replaceSeriesList(segmentId, [row, ...current])
      return
    }

    const updated = [...current]
    updated[index] = row
    replaceSeriesList(segmentId, updated)
  }

  function removeSeries(segmentId: number, seriesId: string) {
    replaceSeriesList(
      segmentId,
      listForSegment(segmentId).filter(item => item.id !== seriesId),
    )
  }

  function stopPolling() {
    if (!pollInterval) return
    clearInterval(pollInterval)
    pollInterval = null
  }

  async function fetchSeries(
    segmentId: number,
    options: FetchSeriesOptions = {},
  ) {
    if (!options.silent) {
      loadingBySegment[segmentId] = true
    }

    try {
      const rows = await $fetch<NarrationImageSeries[]>(
        `${baseURL}/api/segments/${segmentId}/image-series`,
      )
      replaceSeriesList(segmentId, rows)
      errorBySegment[segmentId] = null
    } catch (err: any) {
      errorBySegment[segmentId] = asErrorMessage(
        err,
        'Failed to load image sequences',
      )
      if (options.throwOnError) {
        throw err
      }
    } finally {
      if (!options.silent) {
        loadingBySegment[segmentId] = false
      }
      if (!options.silent) {
        refreshPolling()
      }
    }
  }

  async function pollActiveSegments() {
    if (pollInFlight) return

    const segmentIds = activeSegmentIds()
    if (!segmentIds.length) {
      stopPolling()
      return
    }

    pollInFlight = true
    try {
      await Promise.all(
        segmentIds.map(segmentId => fetchSeries(segmentId, { silent: true })),
      )
    } finally {
      pollInFlight = false
      if (!activeSegmentIds().length) {
        stopPolling()
      }
    }
  }

  function refreshPolling() {
    const segmentIds = activeSegmentIds()
    if (!segmentIds.length) {
      stopPolling()
      return
    }

    if (pollInterval) return
    pollInterval = setInterval(() => {
      void pollActiveSegments()
    }, 2500)
    void pollActiveSegments()
  }

  async function openPanel(segmentId: number) {
    panelOpenBySegment[segmentId] = true
    if (!seriesBySegment[segmentId]) {
      await fetchSeries(segmentId)
    } else {
      refreshPolling()
    }
  }

  async function ensureSegmentLoaded(segmentId: number) {
    if (seriesBySegment[segmentId]) {
      refreshPolling()
      return
    }
    await fetchSeries(segmentId, { silent: true })
    refreshPolling()
  }

  function closePanel(segmentId: number) {
    delete panelOpenBySegment[segmentId]
  }

  async function togglePanel(segmentId: number) {
    if (isPanelOpen(segmentId)) {
      closePanel(segmentId)
      return
    }
    await openPanel(segmentId)
  }

  function clearSegment(segmentId: number) {
    delete panelOpenBySegment[segmentId]
    delete seriesBySegment[segmentId]
    delete loadingBySegment[segmentId]
    delete errorBySegment[segmentId]
    delete creatingBySegment[segmentId]
    refreshPolling()
  }

  function clearAll() {
    stopPolling()

    for (const segmentId of loadedSegmentIds()) {
      delete panelOpenBySegment[segmentId]
      delete seriesBySegment[segmentId]
      delete loadingBySegment[segmentId]
      delete errorBySegment[segmentId]
      delete creatingBySegment[segmentId]
    }

    for (const seriesId of Object.keys(busyBySeries)) {
      delete busyBySeries[seriesId]
    }
    for (const seriesId of Object.keys(suggestingBySeries)) {
      delete suggestingBySeries[seriesId]
    }
  }

  async function withSeriesBusy<T>(seriesId: string, action: () => Promise<T>) {
    busyBySeries[seriesId] = true
    try {
      return await action()
    } finally {
      busyBySeries[seriesId] = false
    }
  }

  async function createManualSeries(
    segmentId: number,
    input: NarrationImageManualSeriesInput,
  ) {
    creatingBySegment[segmentId] = true
    errorBySegment[segmentId] = null

    try {
      const created = await $fetch<NarrationImageSeries>(
        `${baseURL}/api/segments/${segmentId}/image-series`,
        {
          method: 'POST',
          body: {
            name: input.name?.trim() || undefined,
            initial_prompt: input.initialPrompt.trim(),
            auto_generate: input.autoGenerate ?? true,
          },
        },
      )
      upsertSeries(segmentId, created)
      refreshPolling()
      return created
    } catch (err: any) {
      errorBySegment[segmentId] = asErrorMessage(
        err,
        'Failed to create image sequence',
      )
      throw err
    } finally {
      creatingBySegment[segmentId] = false
    }
  }

  async function createAutoSeries(
    segmentId: number,
    input: NarrationImageAutoSeriesInput,
  ) {
    creatingBySegment[segmentId] = true
    errorBySegment[segmentId] = null

    try {
      const created = await $fetch<NarrationImageSeries>(
        `${baseURL}/api/segments/${segmentId}/image-series/auto`,
        {
          method: 'POST',
          body: {
            name: input.name?.trim() || undefined,
            creative_direction: input.creativeDirection.trim(),
            target_images: input.targetImages || 4,
          },
        },
      )
      upsertSeries(segmentId, created)
      refreshPolling()
      return created
    } catch (err: any) {
      errorBySegment[segmentId] = asErrorMessage(
        err,
        'Failed to generate sequence plan',
      )
      throw err
    } finally {
      creatingBySegment[segmentId] = false
    }
  }

  async function queueSeries(segmentId: number, seriesId: string) {
    errorBySegment[segmentId] = null
    const updated = await withSeriesBusy(seriesId, async () => (
      $fetch<NarrationImageSeries>(`${baseURL}/api/image-series/${seriesId}/generate`, {
        method: 'POST',
      })
    ))
    upsertSeries(segmentId, updated)
    refreshPolling()
    return updated
  }

  async function deleteSeries(segmentId: number, seriesId: string) {
    errorBySegment[segmentId] = null
    await withSeriesBusy(seriesId, async () => (
      $fetch(`${baseURL}/api/image-series/${seriesId}`, { method: 'DELETE' })
    ))
    removeSeries(segmentId, seriesId)
    refreshPolling()
  }

  async function addFrame(
    segmentId: number,
    seriesId: string,
    input: NarrationImageAddFrameInput,
  ) {
    errorBySegment[segmentId] = null
    await withSeriesBusy(seriesId, async () => {
      await $fetch(`${baseURL}/api/image-series/${seriesId}/frames`, {
        method: 'POST',
        body: {
          prompt: input.prompt.trim(),
          parent_frame_id: input.parentFrameId || undefined,
          is_fork: input.isFork ?? false,
          mode: input.mode || undefined,
        },
      })
      await fetchSeries(segmentId, { silent: true, throwOnError: true })
    })
    refreshPolling()
  }

  async function regenerateFrame(
    segmentId: number,
    seriesId: string,
    frameId: string,
    input: NarrationImageRegenerateFrameInput = {},
  ) {
    errorBySegment[segmentId] = null
    const updated = await withSeriesBusy(seriesId, async () => (
      $fetch<NarrationImageSeries>(
        `${baseURL}/api/image-series/${seriesId}/frames/${frameId}/regenerate`,
        {
          method: 'POST',
          body: {
            include_descendants: input.includeDescendants ?? true,
            auto_generate: input.autoGenerate ?? true,
          },
        },
      )
    ))
    upsertSeries(segmentId, updated)
    refreshPolling()
    return updated
  }

  async function suggestPrompts(
    seriesId: string,
    input: NarrationImageSuggestInput = {},
  ) {
    suggestingBySeries[seriesId] = true
    try {
      const data = await $fetch<NarrationImagePromptSuggestionResponse>(
        `${baseURL}/api/image-series/${seriesId}/suggestions`,
        {
          method: 'POST',
          body: {
            source_frame_id: input.sourceFrameId || undefined,
            guidance: input.guidance?.trim() || undefined,
            count: input.count || 3,
          },
        },
      )
      return data.suggestions || []
    } finally {
      suggestingBySeries[seriesId] = false
    }
  }

  watch(
    () => projectId.value,
    () => {
      clearAll()
    },
    { immediate: true },
  )

  onUnmounted(() => {
    stopPolling()
  })

  return {
    mediaUrl,
    isPanelOpen,
    openPanel,
    closePanel,
    togglePanel,
    ensureSegmentLoaded,
    clearSegment,
    clearAll,
    listForSegment,
    latestPreviewFrames,
    isLoadingSegment,
    segmentError,
    isCreatingSegment,
    isSeriesBusy,
    isSeriesSuggesting,
    refreshSegment: segmentId => fetchSeries(segmentId),
    createManualSeries,
    createAutoSeries,
    queueSeries,
    deleteSeries,
    addFrame,
    regenerateFrame,
    suggestPrompts,
  }
}
