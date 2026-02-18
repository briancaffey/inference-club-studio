<script setup lang="ts">
import { ChevronDown, Loader2, RefreshCw, Sparkles } from 'lucide-vue-next'
import type { CutAIStatus } from '~/types'

const props = defineProps<{
  projectId: string
  cutId: string
}>()

const store = useCutAiStore()
const { mediaUrl } = useApi()

const pollInterval = ref<ReturnType<typeof setInterval>>()
const expanded = ref(false)

const state = computed(() => store.stateForCut(props.cutId))
const loading = computed(() => store.isLoading(props.cutId))

const firstFrameSrc = computed(() => mediaUrl(state.value?.first_frame_path ?? null))

const isActive = computed(() => {
  const ai = state.value
  if (!ai) return false
  return ['queued', 'running'].includes(ai.clip_overview_status) || ['queued', 'running'].includes(ai.first_frame_status)
})

function statusVariant(status: string) {
  if (status === 'completed') return 'default'
  if (status === 'error') return 'destructive'
  return 'secondary'
}

function statusLabel(status: CutAIStatus | string) {
  switch (status) {
    case 'pending': return 'Pending'
    case 'queued': return 'Queued'
    case 'running': return 'Running...'
    case 'completed': return 'Ready'
    case 'error': return 'Error'
    default: return status
  }
}

function formatTime(value: string | null | undefined) {
  if (!value) return ''
  return new Date(value).toLocaleString()
}

async function refresh() {
  await store.fetchState(props.projectId, props.cutId)
}

async function regenerate(types: ('clip_overview' | 'first_frame')[]) {
  await store.regenerate(props.projectId, props.cutId, types)
}

watch(isActive, (active) => {
  if (active && !pollInterval.value) {
    pollInterval.value = setInterval(() => {
      store.fetchState(props.projectId, props.cutId)
    }, 3000)
  } else if (!active && pollInterval.value) {
    clearInterval(pollInterval.value)
    pollInterval.value = undefined
  }
})

onMounted(refresh)

onUnmounted(() => {
  if (pollInterval.value) clearInterval(pollInterval.value)
})
</script>

<template>
  <div class="rounded-lg border bg-card">
    <button
      type="button"
      class="flex w-full items-center justify-between px-3 py-3 text-left"
      @click="expanded = !expanded"
    >
      <div class="flex items-center gap-2">
        <Sparkles class="h-4 w-4 text-muted-foreground" />
        <p class="text-sm font-medium">Cut Insights</p>
        <Badge
          v-if="state"
          :variant="
            state.clip_overview_status === 'error' || state.first_frame_status === 'error'
              ? 'destructive'
              : state.clip_overview_status === 'completed' && state.first_frame_status === 'completed'
                ? 'default'
                : 'secondary'
          "
          class="text-[11px]"
        >
          {{
            state.clip_overview_status === 'completed' && state.first_frame_status === 'completed'
              ? 'Ready'
              : state.clip_overview_status === 'error' || state.first_frame_status === 'error'
                ? 'Needs Attention'
                : 'In Progress'
          }}
        </Badge>
      </div>
      <ChevronDown
        class="h-4 w-4 text-muted-foreground transition-transform"
        :class="expanded ? 'rotate-180' : ''"
      />
    </button>

    <div v-if="expanded" class="space-y-3 border-t px-3 pb-3 pt-3">
      <div class="flex items-center justify-end gap-1">
        <Button
          variant="outline"
          size="sm"
          :disabled="loading"
          @click="regenerate(['clip_overview', 'first_frame'])"
        >
          <RefreshCw class="mr-1.5 h-3.5 w-3.5" />
          Regenerate All
        </Button>
        <Button variant="ghost" size="icon" :disabled="loading" @click="refresh">
          <Loader2 v-if="loading" class="h-4 w-4 animate-spin" />
          <RefreshCw v-else class="h-4 w-4" />
        </Button>
      </div>

      <div v-if="!state" class="text-sm text-muted-foreground">
        Loading insights...
      </div>

      <template v-else>
        <div class="space-y-2 rounded-md border p-3">
          <div class="flex items-start justify-between gap-2">
            <div class="space-y-1">
              <p class="text-sm font-medium">Clip Overview</p>
              <Badge :variant="statusVariant(state.clip_overview_status as string)" class="text-xs">
                {{ statusLabel(state.clip_overview_status) }}
              </Badge>
            </div>
            <div class="flex items-center gap-1">
              <CopyButton
                :text="state.clip_overview_text"
                tooltip="Copy clip overview"
                class="h-8 w-8"
              />
              <Button
                variant="ghost"
                size="icon"
                class="h-8 w-8"
                :disabled="loading"
                @click="regenerate(['clip_overview'])"
              >
                <RefreshCw class="h-4 w-4" />
              </Button>
            </div>
          </div>
          <p v-if="state.clip_overview_text" class="whitespace-pre-wrap text-sm">
            {{ state.clip_overview_text }}
          </p>
          <p v-else class="text-sm text-muted-foreground">
            No overview generated yet.
          </p>
          <p v-if="state.clip_overview_run?.completed_at" class="text-xs text-muted-foreground">
            Updated {{ formatTime(state.clip_overview_run.completed_at) }}
          </p>
        </div>

        <div class="space-y-2 rounded-md border p-3">
          <div class="flex items-start justify-between gap-2">
            <div class="space-y-1">
              <p class="text-sm font-medium">First Frame Description</p>
              <Badge :variant="statusVariant(state.first_frame_status as string)" class="text-xs">
                {{ statusLabel(state.first_frame_status) }}
              </Badge>
            </div>
            <div class="flex items-center gap-1">
              <CopyButton
                :text="state.first_frame_description_text"
                tooltip="Copy first-frame description"
                class="h-8 w-8"
              />
              <Button
                variant="ghost"
                size="icon"
                class="h-8 w-8"
                :disabled="loading"
                @click="regenerate(['first_frame'])"
              >
                <RefreshCw class="h-4 w-4" />
              </Button>
            </div>
          </div>
          <div class="flex flex-col gap-2 sm:flex-row sm:items-start">
            <img
              v-if="firstFrameSrc"
              :src="firstFrameSrc"
              alt="First frame"
              class="h-24 w-24 rounded object-cover"
            />
            <p v-if="state.first_frame_description_text" class="whitespace-pre-wrap text-sm">
              {{ state.first_frame_description_text }}
            </p>
            <p v-else class="text-sm text-muted-foreground">
              No first-frame description generated yet.
            </p>
          </div>
          <p v-if="state.first_frame_run?.completed_at" class="text-xs text-muted-foreground">
            Updated {{ formatTime(state.first_frame_run.completed_at) }}
          </p>
        </div>

        <p v-if="state.last_error_message" class="text-xs text-destructive">
          {{ state.last_error_message }}
        </p>
      </template>
    </div>
  </div>
</template>
