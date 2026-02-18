import { defineStore } from 'pinia'
import type { Take } from '~/types'

export const useTakesStore = defineStore('takes', () => {
  const { baseURL } = useApi()

  const takes = ref<Record<string, Take[]>>({})
  const loading = ref(false)
  const error = ref<string | null>(null)

  function takesForGeneration(generationId: string): Take[] {
    return takes.value[generationId] || []
  }

  function _apiBase(projectId: string, cutId: string, generationId: string) {
    return `${baseURL}/api/v1/projects/${projectId}/cuts/${cutId}/generations/${generationId}/takes`
  }

  async function fetchTakes(projectId: string, cutId: string, generationId: string) {
    error.value = null
    try {
      const data = await $fetch<Take[]>(_apiBase(projectId, cutId, generationId))
      takes.value[generationId] = data
    } catch (e: any) {
      error.value = e.message || 'Failed to fetch takes'
    }
  }

  async function createTake(
    projectId: string,
    cutId: string,
    generationId: string,
    params: {
      prompt: string
      width?: number
      height?: number
      frame_count?: number
      seed?: number
    },
  ) {
    error.value = null
    try {
      const data = await $fetch<Take>(_apiBase(projectId, cutId, generationId), {
        method: 'POST',
        body: params,
      })
      if (!takes.value[generationId]) {
        takes.value[generationId] = []
      }
      takes.value[generationId].unshift(data)
      return data
    } catch (e: any) {
      error.value = e.message || 'Failed to create take'
      throw e
    }
  }

  async function deleteTake(
    projectId: string,
    cutId: string,
    generationId: string,
    takeId: string,
  ) {
    error.value = null
    try {
      await $fetch(`${_apiBase(projectId, cutId, generationId)}/${takeId}`, {
        method: 'DELETE',
      })
      if (takes.value[generationId]) {
        takes.value[generationId] = takes.value[generationId].filter(t => t.id !== takeId)
      }
    } catch (e: any) {
      error.value = e.message || 'Failed to delete take'
      throw e
    }
  }

  function hasActiveTakes(generationId: string): boolean {
    const genTakes = takes.value[generationId] || []
    return genTakes.some(t =>
      ['pending', 'uploading_assets', 'generating', 'downloading', 'encoding_canny'].includes(
        t.status,
      ),
    )
  }

  return {
    takes,
    loading,
    error,
    takesForGeneration,
    fetchTakes,
    createTake,
    deleteTake,
    hasActiveTakes,
  }
})
