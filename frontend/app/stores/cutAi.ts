import { defineStore } from 'pinia'
import type { CutAIAnalysisType, CutAIRun, CutAIState, FluxPromptDraftResponse } from '~/types'

export const useCutAiStore = defineStore('cutAi', () => {
  const { baseURL } = useApi()

  const states = ref<Record<string, CutAIState>>({})
  const runs = ref<Record<string, CutAIRun[]>>({})
  const lastDraft = ref<Record<string, FluxPromptDraftResponse | null>>({})
  const loadingByCut = ref<Record<string, boolean>>({})
  const error = ref<string | null>(null)

  function stateForCut(cutId: string): CutAIState | null {
    return states.value[cutId] || null
  }

  function runsForCut(cutId: string): CutAIRun[] {
    return runs.value[cutId] || []
  }

  function isLoading(cutId: string): boolean {
    return !!loadingByCut.value[cutId]
  }

  function _base(projectId: string, cutId: string): string {
    return `${baseURL}/api/v1/projects/${projectId}/cuts/${cutId}/ai`
  }

  async function fetchState(projectId: string, cutId: string) {
    loadingByCut.value[cutId] = true
    error.value = null
    try {
      const data = await $fetch<CutAIState>(_base(projectId, cutId))
      states.value[cutId] = data
      return data
    } catch (e: any) {
      error.value = e.message || 'Failed to fetch cut AI state'
      throw e
    } finally {
      loadingByCut.value[cutId] = false
    }
  }

  async function regenerate(
    projectId: string,
    cutId: string,
    types: CutAIAnalysisType[] = ['clip_overview', 'first_frame'],
  ) {
    loadingByCut.value[cutId] = true
    error.value = null
    try {
      const data = await $fetch<CutAIState>(`${_base(projectId, cutId)}/regenerate`, {
        method: 'POST',
        body: { types },
      })
      states.value[cutId] = data
      return data
    } catch (e: any) {
      error.value = e.message || 'Failed to regenerate cut AI descriptions'
      throw e
    } finally {
      loadingByCut.value[cutId] = false
    }
  }

  async function fetchRuns(projectId: string, cutId: string, analysisType?: string) {
    error.value = null
    try {
      const data = await $fetch<CutAIRun[]>(
        `${_base(projectId, cutId)}/runs`,
        { query: analysisType ? { analysis_type: analysisType } : undefined },
      )
      runs.value[cutId] = data
      return data
    } catch (e: any) {
      error.value = e.message || 'Failed to fetch cut AI runs'
      throw e
    }
  }

  async function createFluxPromptDraft(
    projectId: string,
    cutId: string,
    params: {
      style: string
      content?: string
    },
  ) {
    loadingByCut.value[cutId] = true
    error.value = null
    try {
      const data = await $fetch<FluxPromptDraftResponse>(`${_base(projectId, cutId)}/prompt-drafts/flux`, {
        method: 'POST',
        body: params,
      })
      lastDraft.value[cutId] = data
      await fetchRuns(projectId, cutId)
      return data
    } catch (e: any) {
      error.value = e.message || 'Failed to generate Flux prompt draft'
      throw e
    } finally {
      loadingByCut.value[cutId] = false
    }
  }

  return {
    states,
    runs,
    lastDraft,
    loadingByCut,
    error,
    stateForCut,
    runsForCut,
    isLoading,
    fetchState,
    fetchRuns,
    regenerate,
    createFluxPromptDraft,
  }
})
