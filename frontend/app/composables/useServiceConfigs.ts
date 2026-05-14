import type {
  ServiceConfigKey,
  ServiceConfigResponse,
  AllConfigsResponse,
  ConfigAuditResponse,
} from '~/types'

export function useServiceConfigs() {
  const { baseURL } = useApi()

  async function fetchAllConfigs(): Promise<AllConfigsResponse> {
    return $fetch<AllConfigsResponse>(`${baseURL}/api/v1/service-configs/`)
  }

  async function getConfig(
    serviceKey: ServiceConfigKey,
  ): Promise<ServiceConfigResponse> {
    return $fetch<ServiceConfigResponse>(
      `${baseURL}/api/v1/service-configs/${serviceKey}`,
    )
  }

  async function updateConfig(
    serviceKey: ServiceConfigKey,
    updates: Record<string, unknown>,
    validate = true,
  ): Promise<ServiceConfigResponse> {
    return $fetch<ServiceConfigResponse>(
      `${baseURL}/api/v1/service-configs/${serviceKey}`,
      {
        method: 'PATCH',
        body: { updates, validate },
      },
    )
  }

  async function getAuditHistory(
    serviceKey: ServiceConfigKey,
  ): Promise<ConfigAuditResponse> {
    return $fetch<ConfigAuditResponse>(
      `${baseURL}/api/v1/service-configs/audit/${serviceKey}`,
    )
  }

  return {
    fetchAllConfigs,
    getConfig,
    updateConfig,
    getAuditHistory,
  }
}
