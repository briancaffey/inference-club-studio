import { defineStore } from 'pinia'
import type {
  InferenceServiceHealth,
  InferenceServicesHealthResponse,
} from '~/types'

const DEFAULT_POLL_INTERVAL_MS = 30_000

export const useServicesStore = defineStore('services', () => {
  const { baseURL } = useApi()

  const report = ref<InferenceServicesHealthResponse | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)

  let pollTimer: ReturnType<typeof setInterval> | null = null
  let isFetching = false

  const services = computed<InferenceServiceHealth[]>(
    () => report.value?.services ?? [],
  )
  const totalServices = computed(
    () => report.value?.total_services ?? services.value.length,
  )
  const healthyServices = computed(
    () =>
      report.value?.healthy_services ??
      services.value.filter(service => service.healthy).length,
  )
  const checkedAt = computed(() => report.value?.checked_at ?? null)
  const status = computed(() => report.value?.status ?? 'degraded')
  const allHealthy = computed(
    () => totalServices.value > 0 && healthyServices.value === totalServices.value,
  )
  const degradedCount = computed(
    () => Math.max(totalServices.value - healthyServices.value, 0),
  )

  async function fetchHealth(options: { silent?: boolean } = {}) {
    if (isFetching) return

    isFetching = true
    if (!options.silent) loading.value = true

    try {
      const data = await $fetch<InferenceServicesHealthResponse>(
        `${baseURL}/api/v1/services/health`,
      )
      report.value = data
      error.value = null
    } catch (e: any) {
      error.value = e?.data?.detail || e?.message || 'Failed to fetch service health'
    } finally {
      if (!options.silent) loading.value = false
      isFetching = false
    }
  }

  function startPolling(intervalMs = DEFAULT_POLL_INTERVAL_MS) {
    if (import.meta.server || pollTimer !== null) return

    pollTimer = setInterval(() => {
      void fetchHealth({ silent: true })
    }, intervalMs)
  }

  function stopPolling() {
    if (pollTimer === null) return
    clearInterval(pollTimer)
    pollTimer = null
  }

  return {
    report,
    loading,
    error,
    services,
    totalServices,
    healthyServices,
    checkedAt,
    status,
    allHealthy,
    degradedCount,
    fetchHealth,
    startPolling,
    stopPolling,
  }
})
