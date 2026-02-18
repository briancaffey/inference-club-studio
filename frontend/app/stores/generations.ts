import { defineStore } from 'pinia'
import type { Generation } from '~/types'

export const useGenerationsStore = defineStore('generations', () => {
  const { baseURL } = useApi()

  const generations = ref<Record<string, Generation[]>>({})
  const loading = ref(false)
  const error = ref<string | null>(null)

  function generationsForCut(cutId: string): Generation[] {
    return generations.value[cutId] || []
  }

  async function fetchGenerations(projectId: string, cutId: string) {
    error.value = null
    try {
      const data = await $fetch<Generation[]>(
        `${baseURL}/api/v1/projects/${projectId}/cuts/${cutId}/generations`,
      )
      generations.value[cutId] = data
    } catch (e: any) {
      error.value = e.message || 'Failed to fetch generations'
    }
  }

  async function createGeneration(
    projectId: string,
    cutId: string,
    params: {
      prompt: string
      width?: number
      height?: number
      num_steps?: number
      cfg_scale?: number
      seed?: number
    },
  ) {
    error.value = null
    try {
      const data = await $fetch<Generation>(
        `${baseURL}/api/v1/projects/${projectId}/cuts/${cutId}/generations`,
        { method: 'POST', body: params },
      )
      if (!generations.value[cutId]) {
        generations.value[cutId] = []
      }
      generations.value[cutId].unshift(data)
      return data
    } catch (e: any) {
      error.value = e.message || 'Failed to create generation'
      throw e
    }
  }

  async function deleteGeneration(
    projectId: string,
    cutId: string,
    generationId: string,
  ) {
    error.value = null
    try {
      await $fetch(
        `${baseURL}/api/v1/projects/${projectId}/cuts/${cutId}/generations/${generationId}`,
        { method: 'DELETE' },
      )
      if (generations.value[cutId]) {
        generations.value[cutId] = generations.value[cutId].filter(
          g => g.id !== generationId,
        )
      }
    } catch (e: any) {
      error.value = e.message || 'Failed to delete generation'
      throw e
    }
  }

  function hasActiveGenerations(cutId: string): boolean {
    const cutGens = generations.value[cutId] || []
    return cutGens.some(g =>
      ['pending', 'extracting_frame', 'uploading_reference', 'generating', 'downloading'].includes(
        g.status,
      ),
    )
  }

  return {
    generations,
    loading,
    error,
    generationsForCut,
    fetchGenerations,
    createGeneration,
    deleteGeneration,
    hasActiveGenerations,
  }
})
