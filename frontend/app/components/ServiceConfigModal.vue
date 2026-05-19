<script setup lang="ts">
import { ref, computed } from 'vue'
import { Save, Clock, AlertCircle, Loader2 } from 'lucide-vue-next'

interface Props {
  open: boolean
  serviceKey: string
  serviceName: string
  config?: Record<string, unknown>
  schemaFields?: string[]
}

const props = defineProps<Props>()
const emit = defineEmits<{
  (e: 'update:open', value: boolean): void
}>()

const { updateConfig, getAuditHistory } = useServiceConfigs()

const saving = ref(false)
const error = ref<string | null>(null)
const auditLoading = ref(false)
const audits = ref<any[]>([])
const activeTab = ref<'config' | 'audit'>('config')

const formValues = ref<Record<string, unknown>>({})

const llmModels = ref<string[]>([])
const llmModelsLoading = ref(false)
const llmModelsError = ref<string | null>(null)
const lastFetchedBaseUrl = ref<string>('')

const isOpen = computed({
  get: () => props.open,
  set: (value) => emit('update:open', value),
})

type EnumOption = { value: string; label: string }
const ENUM_FIELD_OPTIONS: Record<string, Record<string, EnumOption[]>> = {
  image_generation: {
    provider: [
      { value: 'invokeai', label: 'InvokeAI' },
      { value: 'flux2_klein', label: 'Flux 2 Klein NIM' },
      { value: 'openai_image', label: 'OpenAI Image API (local server)' },
    ],
  },
  stt: {
    provider: [
      { value: 'nemotron', label: 'NVIDIA Nemotron (custom /transcribe)' },
      { value: 'openai', label: 'OpenAI-compatible (/v1/audio/transcriptions)' },
    ],
  },
}

function getEnumOptions(field: string): EnumOption[] | undefined {
  return ENUM_FIELD_OPTIONS[props.serviceKey]?.[field]
}

const shouldFetchModels = computed(() => {
  if (props.serviceKey === 'llm') return true
  if (props.serviceKey === 'stt' && formValues.value.provider === 'openai') return true
  return false
})

onMounted(() => {
  if (props.config) {
    formValues.value = { ...props.config }
  }
  if (
    shouldFetchModels.value &&
    typeof formValues.value.base_url === 'string' &&
    formValues.value.base_url
  ) {
    void fetchLlmModels(formValues.value.base_url as string)
  }
})

watch(
  () => props.config,
  (newConfig) => {
    if (newConfig) {
      formValues.value = { ...newConfig }
      if (
        shouldFetchModels.value &&
        typeof newConfig.base_url === 'string' &&
        newConfig.base_url
      ) {
        void fetchLlmModels(newConfig.base_url as string)
      }
    }
  },
  { deep: true },
)

watch(
  () => formValues.value.provider,
  (newProvider) => {
    if (props.serviceKey !== 'stt') return
    if (newProvider === 'openai') {
      const baseUrl = formValues.value.base_url
      if (typeof baseUrl === 'string' && baseUrl) {
        void fetchLlmModels(baseUrl)
      }
    } else {
      llmModels.value = []
      llmModelsError.value = null
      lastFetchedBaseUrl.value = ''
    }
  },
)

function normalizeBaseUrl(url: string): string {
  return url.trim().replace(/\/+$/, '')
}

function buildModelsUrl(baseUrl: string): string {
  const stripped = baseUrl.replace(/\/v1$/, '')
  return `${stripped}/v1/models`
}

async function fetchLlmModels(baseUrl: string) {
  const normalized = normalizeBaseUrl(baseUrl)
  if (!normalized) {
    llmModels.value = []
    llmModelsError.value = null
    lastFetchedBaseUrl.value = ''
    return
  }
  llmModelsLoading.value = true
  llmModelsError.value = null
  try {
    const headers: Record<string, string> = {}
    const apiKey = formValues.value.api_key
    if (typeof apiKey === 'string' && apiKey) {
      headers.Authorization = `Bearer ${apiKey}`
    }
    const response = await $fetch<any>(buildModelsUrl(normalized), { headers })
    const data: any[] = Array.isArray(response?.data)
      ? response.data
      : Array.isArray(response)
        ? response
        : []
    const ids = data
      .map((m) => (typeof m === 'string' ? m : m?.id))
      .filter((id): id is string => typeof id === 'string' && !!id)
    llmModels.value = ids
    lastFetchedBaseUrl.value = normalized

    const currentModel = formValues.value.model
    if (ids.length === 1) {
      formValues.value.model = ids[0]
    } else if (
      ids.length > 1 &&
      typeof currentModel === 'string' &&
      currentModel &&
      !ids.includes(currentModel)
    ) {
      formValues.value.model = ''
    }
  } catch (e: any) {
    llmModels.value = []
    llmModelsError.value =
      e?.data?.detail || e?.message || 'Failed to fetch models from /v1/models'
  } finally {
    llmModelsLoading.value = false
  }
}

function handleBaseUrlBlur() {
  if (!shouldFetchModels.value) return
  const baseUrl = formValues.value.base_url
  if (typeof baseUrl !== 'string') return
  const normalized = normalizeBaseUrl(baseUrl)
  if (normalized && normalized !== lastFetchedBaseUrl.value) {
    void fetchLlmModels(normalized)
  }
}

async function handleSave() {
  saving.value = true
  error.value = null

  const updates: Record<string, unknown> = {}
  for (const key of Object.keys(formValues.value)) {
    if (key && formValues.value[key] !== undefined) {
      updates[key] = formValues.value[key]
    }
  }

  try {
    await updateConfig(props.serviceKey as any, updates)
    isOpen.value = false
  } catch (e: any) {
    error.value = e?.data?.detail || e?.message || 'Failed to save config'
  } finally {
    saving.value = false
  }
}

async function loadAuditHistory() {
  auditLoading.value = true
  try {
    const response = await getAuditHistory(props.serviceKey as any)
    audits.value = response.audits || []
  } catch (e: any) {
    audits.value = []
  } finally {
    auditLoading.value = false
  }
}

function getFieldPlaceholder(field: string): string {
  if (field.includes('url') || field.includes('base_url')) {
    return 'http://localhost:port'
  }
  if (field.includes('timeout')) {
    return '60.0'
  }
  if (field.includes('interval')) {
    return '5.0'
  }
  if (field.includes('max') || field.includes('count')) {
    return '3'
  }
  if (field.includes('model')) {
    return 'gpt-4'
  }
  if (field.includes('board_id')) {
    return 'your-board-id'
  }
  return ''
}

function isNumberField(field: string): boolean {
  return (
    field.includes('timeout') ||
    field.includes('interval') ||
    field.includes('max') ||
    field.includes('count') ||
    field.includes('steps') ||
    field.includes('scale') ||
    field.includes('seed') ||
    field.includes('rate') ||
    field.includes('width') ||
    field.includes('height')
  )
}

function isBooleanField(field: string): boolean {
  return (
    field.includes('auto') ||
    field.includes('enable') ||
    field.includes('disable') ||
    field === 'validate'
  )
}
</script>

<template>
  <Dialog v-model:open="isOpen">
    <DialogContent class="sm:max-w-2xl max-h-[90vh] overflow-y-auto">
      <DialogHeader>
        <DialogTitle class="flex items-center gap-2">
          Configure {{ serviceName }}
        </DialogTitle>
        <DialogDescription>
          Manage settings for the {{ serviceKey }} service.
        </DialogDescription>
      </DialogHeader>

      <Tabs v-model:model-value="activeTab" class="mt-4">
        <TabsList class="grid w-full grid-cols-2">
          <TabsTrigger value="config">Configuration</TabsTrigger>
          <TabsTrigger value="audit">Audit History</TabsTrigger>
        </TabsList>

        <TabsContent value="config" class="mt-4">
          <div v-if="schemaFields && schemaFields.length > 0" class="space-y-4">
            <div
              v-for="field in schemaFields"
              :key="field"
              class="grid gap-2"
            >
              <Label :for="`config-${field}`">{{ field }}</Label>

              <Input
                v-if="isNumberField(field)"
                :id="`config-${field}`"
                v-model.number="formValues[field]"
                type="number"
                step="any"
                :placeholder="getFieldPlaceholder(field)"
              />

              <Input
                v-else-if="isBooleanField(field)"
                :id="`config-${field}`"
                v-model="formValues[field]"
                type="checkbox"
              />

              <template v-else-if="shouldFetchModels && field === 'base_url'">
                <Input
                  :id="`config-${field}`"
                  v-model="formValues[field]"
                  type="text"
                  :placeholder="getFieldPlaceholder(field)"
                  @blur="handleBaseUrlBlur"
                />
                <div class="flex items-center gap-2 text-xs text-muted-foreground">
                  <Loader2 v-if="llmModelsLoading" class="h-3 w-3 animate-spin" />
                  <span v-if="llmModelsLoading">Fetching models from /v1/models…</span>
                  <span v-else-if="llmModelsError" class="text-red-600 dark:text-red-400">
                    {{ llmModelsError }}
                  </span>
                  <span v-else-if="llmModels.length > 0">
                    {{ llmModels.length }} model{{ llmModels.length === 1 ? '' : 's' }} available
                  </span>
                </div>
              </template>

              <template v-else-if="shouldFetchModels && field === 'model'">
                <Select
                  v-if="llmModels.length > 0"
                  :model-value="(formValues[field] as string) || undefined"
                  @update:model-value="formValues[field] = $event"
                >
                  <SelectTrigger :id="`config-${field}`" class="w-full">
                    <SelectValue placeholder="Select a model" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem
                      v-for="modelId in llmModels"
                      :key="modelId"
                      :value="modelId"
                    >
                      {{ modelId }}
                    </SelectItem>
                  </SelectContent>
                </Select>
                <Input
                  v-else
                  :id="`config-${field}`"
                  v-model="formValues[field]"
                  type="text"
                  :placeholder="
                    llmModelsLoading
                      ? 'Loading models…'
                      : 'Enter base_url above to load models'
                  "
                  :disabled="llmModelsLoading"
                />
              </template>

              <Select
                v-else-if="getEnumOptions(field)"
                :model-value="(formValues[field] as string) || getEnumOptions(field)![0].value"
                @update:model-value="formValues[field] = $event"
              >
                <SelectTrigger :id="`config-${field}`" class="w-full">
                  <SelectValue placeholder="Select an option" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem
                    v-for="opt in getEnumOptions(field)"
                    :key="opt.value"
                    :value="opt.value"
                  >
                    {{ opt.label }}
                  </SelectItem>
                </SelectContent>
              </Select>

              <Input
                v-else
                :id="`config-${field}`"
                v-model="formValues[field]"
                type="text"
                :placeholder="getFieldPlaceholder(field)"
              />
            </div>
          </div>

          <p v-else class="text-sm text-muted-foreground">
            No configuration fields available.
          </p>

          <Alert v-if="error" class="mt-4 bg-red-50 dark:bg-red-950 border-red-200 dark:border-red-900">
            <AlertCircle class="h-4 w-4 text-red-600 dark:text-red-400" />
            <AlertTitle>Error</AlertTitle>
            <AlertDescription>{{ error }}</AlertDescription>
          </Alert>

          <div class="flex justify-end gap-2 mt-6">
            <Button variant="outline" @click="isOpen = false">Cancel</Button>
            <Button :disabled="saving" @click="handleSave">
              <Save v-if="!saving" class="mr-2 h-4 w-4" />
              <Loader2 v-else class="mr-2 h-4 w-4 animate-spin" />
              {{ saving ? 'Saving...' : 'Save Changes' }}
            </Button>
          </div>
        </TabsContent>

        <TabsContent value="audit" class="mt-4">
          <div v-if="audits.length === 0 && !auditLoading" class="text-center py-8">
            <Clock class="mx-auto h-12 w-12 text-muted-foreground" />
            <p class="mt-2 text-sm text-muted-foreground">No audit history available</p>
            <Button variant="outline" class="mt-4" @click="loadAuditHistory">
              Load Audit History
            </Button>
          </div>

          <div v-if="auditLoading" class="flex items-center justify-center py-8">
            <Loader2 class="h-6 w-6 animate-spin text-muted-foreground" />
            <span class="ml-2 text-sm text-muted-foreground">Loading...</span>
          </div>

          <div v-else-if="audits.length > 0" class="space-y-4 max-h-96 overflow-y-auto">
            <Card
              v-for="audit in audits"
              :key="audit.id"
              class="bg-muted/50"
            >
              <CardHeader class="pb-2">
                <div class="flex items-center justify-between">
                  <span class="text-sm font-medium">
                    {{ audit.updated_by || 'Unknown User' }}
                  </span>
                  <span class="text-xs text-muted-foreground">
                    {{ new Date(audit.created_at).toLocaleString() }}
                  </span>
                </div>
              </CardHeader>
              <CardContent class="pt-2">
                <div class="text-xs text-muted-foreground">
                  Changed fields: {{ (audit.changed_fields || []).join(', ') }}
                </div>
              </CardContent>
            </Card>
          </div>
        </TabsContent>
      </Tabs>
    </DialogContent>
  </Dialog>
</template>
