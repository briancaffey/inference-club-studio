import { defineStore } from 'pinia'
import type { Cut, Project } from '~/types'

export const useProjectsStore = defineStore('projects', () => {
  const { baseURL } = useApi()

  const projects = ref<Project[]>([])
  const currentProject = ref<Project | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)

  async function fetchProjects() {
    loading.value = true
    error.value = null
    try {
      const data = await $fetch<Project[]>(`${baseURL}/api/v1/projects`)
      projects.value = data
    } catch (e: any) {
      error.value = e.message || 'Failed to fetch projects'
    } finally {
      loading.value = false
    }
  }

  async function fetchProject(id: string) {
    loading.value = true
    error.value = null
    try {
      const data = await $fetch<Project>(`${baseURL}/api/v1/projects/${id}`)
      currentProject.value = data
    } catch (e: any) {
      error.value = e.message || 'Failed to fetch project'
    } finally {
      loading.value = false
    }
  }

  async function createProject(name: string, description?: string) {
    error.value = null
    try {
      const data = await $fetch<Project>(`${baseURL}/api/v1/projects`, {
        method: 'POST',
        body: { name, description },
      })
      projects.value.unshift(data)
      return data
    } catch (e: any) {
      error.value = e.message || 'Failed to create project'
      throw e
    }
  }

  async function updateProject(id: string, updates: { name?: string; description?: string }) {
    error.value = null
    try {
      const data = await $fetch<Project>(`${baseURL}/api/v1/projects/${id}`, {
        method: 'PATCH',
        body: updates,
      })
      const idx = projects.value.findIndex(p => p.id === id)
      if (idx !== -1) projects.value[idx] = { ...projects.value[idx], ...data }
      if (currentProject.value?.id === id) {
        currentProject.value = { ...currentProject.value, ...data }
      }
      return data
    } catch (e: any) {
      error.value = e.message || 'Failed to update project'
      throw e
    }
  }

  async function deleteProject(id: string) {
    error.value = null
    try {
      await $fetch(`${baseURL}/api/v1/projects/${id}`, { method: 'DELETE' })
      projects.value = projects.value.filter(p => p.id !== id)
      if (currentProject.value?.id === id) currentProject.value = null
    } catch (e: any) {
      error.value = e.message || 'Failed to delete project'
      throw e
    }
  }

  async function uploadCuts(projectId: string, files: File[]) {
    error.value = null
    try {
      const formData = new FormData()
      files.forEach(f => formData.append('files', f))
      const data = await $fetch<{ uploaded: Cut[] }>(
        `${baseURL}/api/v1/projects/${projectId}/cuts`,
        { method: 'POST', body: formData },
      )
      // Refresh project to get updated cuts list
      await fetchProject(projectId)
      return data.uploaded
    } catch (e: any) {
      error.value = e.message || 'Failed to upload cuts'
      throw e
    }
  }

  async function deleteCut(projectId: string, cutId: string) {
    error.value = null
    try {
      await $fetch(`${baseURL}/api/v1/projects/${projectId}/cuts/${cutId}`, {
        method: 'DELETE',
      })
      await fetchProject(projectId)
    } catch (e: any) {
      error.value = e.message || 'Failed to delete cut'
      throw e
    }
  }

  async function reorderCuts(projectId: string, cutIds: string[]) {
    error.value = null
    try {
      const data = await $fetch<Cut[]>(
        `${baseURL}/api/v1/projects/${projectId}/cuts/reorder`,
        { method: 'PUT', body: { cut_ids: cutIds } },
      )
      if (currentProject.value?.id === projectId) {
        currentProject.value = { ...currentProject.value, cuts: data }
      }
      return data
    } catch (e: any) {
      error.value = e.message || 'Failed to reorder cuts'
      throw e
    }
  }

  return {
    projects,
    currentProject,
    loading,
    error,
    fetchProjects,
    fetchProject,
    createProject,
    updateProject,
    deleteProject,
    uploadCuts,
    deleteCut,
    reorderCuts,
  }
})
