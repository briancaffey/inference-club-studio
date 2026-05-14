<script setup lang="ts">
import { ref, computed } from 'vue'
import { X, Save, Clock, AlertCircle } from 'lucide-vue-next'

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

const loading = ref(false)
const saving = ref(false)
const error = ref<string | null>(null)
const auditLoading = ref(false)
const audits = ref<any[]>([])
const activeTab = ref<'config' | 'audit'>('config')

const formValues = ref<Record<string, unknown>>({})

const isOpen = computed({
  get: () => props.open,
  set: (value) => emit('update:open', value),
})

onMounted(() => {
  if (props.config) {
    formValues.value = { ...props.config }
  }
})

watch(
  () => props.config,
  (newConfig) => {
    if (newConfig) {
      formValues.value = { ...newConfig }
    }
  },
  { deep: true },
)

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
