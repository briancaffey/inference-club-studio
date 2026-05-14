<script setup lang="ts">
import { ref } from 'vue'
import { storeToRefs } from 'pinia'
import {
  Settings,
  ExternalLink,
  Activity,
  CheckCircle,
  XCircle,
  Loader2,
  Server,
  Database,
} from 'lucide-vue-next'

const config = useRuntimeConfig()
const servicesStore = useServicesStore()
const { fetchAllConfigs } = useServiceConfigs()
const {
  allHealthy,
  checkedAt,
  error: servicesError,
  healthyServices,
  loading: servicesLoading,
  services,
  totalServices,
} = storeToRefs(servicesStore)

const { data: health, error, status, refresh } = useFetch<{ status: string }>(
  `${config.public.apiBase}/api/v1/health`,
  { server: false }
)

const allConfigs = ref<Record<string, any> | null>(null)
const configsLoading = ref(false)
const configsError = ref<string | null>(null)

const selectedConfigKey = ref<string>('')
const selectedConfigName = ref<string>('')
const selectedConfigData = ref<Record<string, unknown>>({})
const selectedSchemaFields = ref<string[]>([])
const modalOpen = ref(false)

const checkedAtLabel = computed(() => {
  if (!checkedAt.value) return 'Not checked yet'
  return new Date(checkedAt.value).toLocaleTimeString()
})

const serviceLabels: Record<string, string> = {
  invokeai: 'InvokeAI',
  comfyui: 'ComfyUI',
  studio_voice: 'Studio Voice',
  llm: 'LLM / OpenAI API',
  dia: 'DIA TTS',
  magpie: 'Magpie TTS',
  stt: 'Speech-to-Text',
  qwen_vl: 'Qwen-VL',
}

async function loadConfigs() {
  configsLoading.value = true
  configsError.value = null
  try {
    allConfigs.value = await fetchAllConfigs()
  } catch (e: any) {
    configsError.value = e?.data?.detail || e?.message || 'Failed to fetch configs'
  } finally {
    configsLoading.value = false
  }
}

function openConfigModal(key: string, name: string) {
  selectedConfigKey.value = key
  selectedConfigName.value = name
  
  if (allConfigs.value && allConfigs.value[key]) {
    selectedConfigData.value = allConfigs.value[key].config || {}
    selectedSchemaFields.value = allConfigs.value[key].schema_fields || []
  } else {
    selectedConfigData.value = {}
    selectedSchemaFields.value = []
  }
  
  modalOpen.value = true
}

function handleModalOpenChange(value: boolean) {
  modalOpen.value = value
  if (!value) {
    loadConfigs()
  }
}

onMounted(() => {
  if (!services.value.length && !servicesLoading.value) {
    void servicesStore.fetchHealth()
  }
  void loadConfigs()
})

function refreshServices() {
  void servicesStore.fetchHealth()
}
</script>

<template>
  <div>
    <PageHeader
      title="Admin"
      description="Manage your Inference Club Studio instance."
    />

    <div class="grid gap-6 sm:grid-cols-2">
      <Card>
        <CardHeader>
          <CardTitle class="flex items-center gap-2">
            <Activity class="h-5 w-5" />
            API Status
          </CardTitle>
          <CardDescription>
            Backend health check.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div class="flex items-center gap-3">
            <template v-if="status === 'idle' || status === 'pending'">
              <Loader2 class="h-5 w-5 animate-spin text-muted-foreground" />
              <span class="text-sm text-muted-foreground">Checking...</span>
            </template>
            <template v-else-if="!error && health?.status === 'ok'">
              <CheckCircle class="h-5 w-5 text-green-500" />
              <span class="text-sm text-green-600 dark:text-green-400">API is healthy</span>
            </template>
            <template v-else>
              <XCircle class="h-5 w-5 text-red-500" />
              <span class="text-sm text-red-600 dark:text-red-400">API unreachable</span>
            </template>
          </div>
        </CardContent>
        <CardFooter>
          <Button variant="outline" size="sm" @click="refresh()">
            Refresh
          </Button>
        </CardFooter>
      </Card>

      <Card id="services" class="sm:col-span-2">
        <CardHeader>
          <CardTitle class="flex items-center gap-2">
            <Server class="h-5 w-5" />
            Inference Services
          </CardTitle>
          <CardDescription>
            Live status for the model services used by this app.
          </CardDescription>
        </CardHeader>
        <CardContent class="space-y-4">
          <div class="flex flex-wrap items-center justify-between gap-2">
            <div class="flex items-center gap-2">
              <Loader2
                v-if="servicesLoading && !services.length"
                class="h-4 w-4 animate-spin text-muted-foreground"
              />
              <CheckCircle
                v-else-if="services.length && allHealthy"
                class="h-4 w-4 text-green-500"
              />
              <XCircle v-else class="h-4 w-4 text-red-500" />
              <span class="text-sm font-medium">
                {{ healthyServices }}/{{ totalServices || '—' }} healthy
              </span>
            </div>
            <span class="text-xs text-muted-foreground">
              Last checked: {{ checkedAtLabel }}
            </span>
          </div>

          <div
            v-if="servicesLoading && !services.length"
            class="flex items-center gap-2 text-sm text-muted-foreground"
          >
            <Loader2 class="h-4 w-4 animate-spin" />
            Checking services...
          </div>

          <div v-else-if="services.length" class="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
            <div
              v-for="service in services"
              :key="service.key"
              class="rounded-lg border p-3"
            >
              <div class="flex items-center justify-between gap-2">
                <div class="flex items-center gap-2">
                  <CheckCircle
                    v-if="service.healthy"
                    class="h-4 w-4 text-green-500"
                  />
                  <XCircle v-else class="h-4 w-4 text-red-500" />
                  <span class="text-sm font-medium">{{ service.name }}</span>
                </div>
                <span
                  :class="[
                    'text-xs font-medium',
                    service.healthy
                      ? 'text-green-600 dark:text-green-400'
                      : 'text-red-600 dark:text-red-400',
                  ]"
                >
                  {{ service.healthy ? 'Healthy' : 'Unreachable' }}
                </span>
              </div>
              <p class="mt-2 break-all text-xs text-muted-foreground">
                {{ service.url }}
              </p>
            </div>
          </div>

          <p
            v-else-if="servicesError"
            class="text-sm text-red-600 dark:text-red-400"
          >
            {{ servicesError }}
          </p>

          <p v-else class="text-sm text-muted-foreground">
            Service status not available yet.
          </p>
        </CardContent>
        <CardFooter>
          <Button variant="outline" size="sm" @click="refreshServices()">
            Refresh services
          </Button>
        </CardFooter>
      </Card>

      <Card id="configs" class="sm:col-span-2">
        <CardHeader>
          <CardTitle class="flex items-center gap-2">
            <Database class="h-5 w-5" />
            Service Configurations
          </CardTitle>
          <CardDescription>
            Manage database configurations for inference services.
          </CardDescription>
        </CardHeader>
        <CardContent class="space-y-4">
          <div v-if="configsLoading" class="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 class="h-4 w-4 animate-spin" />
            Loading configurations...
          </div>

          <p v-else-if="configsError" class="text-sm text-red-600 dark:text-red-400">
            {{ configsError }}
          </p>

          <div v-else-if="allConfigs && Object.keys(allConfigs).length > 0" class="grid gap-3 md:grid-cols-2 lg:grid-cols-4">
            <Button
              v-for="(configData, key) in allConfigs"
              :key="key"
              variant="outline"
              class="justify-start h-auto py-3 px-4 flex-col items-start gap-1"
              @click="openConfigModal(key, serviceLabels[key] || key)"
            >
              <span class="text-sm font-medium">{{ serviceLabels[key] || key }}</span>
              <span class="text-xs text-muted-foreground">
                {{ Object.keys(configData.config || {}).length }} fields configured
              </span>
            </Button>
          </div>

          <p v-else class="text-sm text-muted-foreground">
            No service configurations available.
          </p>
        </CardContent>
        <CardFooter>
          <Button variant="outline" size="sm" @click="loadConfigs()">
            Refresh configs
          </Button>
        </CardFooter>
      </Card>

      <ServiceConfigModal
        :open="modalOpen"
        :service-key="selectedConfigKey"
        :service-name="selectedConfigName"
        :config="selectedConfigData"
        :schema-fields="selectedSchemaFields"
        @update:open="handleModalOpenChange"
      />

      <Card>
        <CardHeader>
          <CardTitle>Quick Links</CardTitle>
          <CardDescription>
            Helpful resources and navigation.
          </CardDescription>
        </CardHeader>
        <CardContent class="flex flex-col gap-3">
          <Button variant="outline" as-child class="justify-start">
            <NuxtLink to="/about">
              <ExternalLink class="mr-2 h-4 w-4" />
              About Inference Club Studio
            </NuxtLink>
          </Button>
          <Button variant="outline" as-child class="justify-start">
            <a href="http://localhost:8000/docs" target="_blank">
              <ExternalLink class="mr-2 h-4 w-4" />
              API Documentation
            </a>
          </Button>
          <Button variant="outline" as-child class="justify-start">
            <a href="http://localhost:5555" target="_blank">
              <ExternalLink class="mr-2 h-4 w-4" />
              Flower (Celery Monitor)
            </a>
          </Button>
        </CardContent>
      </Card>
    </div>
  </div>
</template>
