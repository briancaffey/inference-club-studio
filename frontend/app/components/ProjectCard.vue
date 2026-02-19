<script setup lang="ts">
import { Film, Mic2, Trash2 } from 'lucide-vue-next'
import type { Project } from '~/types'

const props = defineProps<{
  project: Project
}>()

const emit = defineEmits<{
  delete: [id: string]
}>()

const store = useProjectsStore()
const deleting = ref(false)

async function handleDelete() {
  if (!confirm(`Delete "${props.project.name}"? This cannot be undone.`)) return
  deleting.value = true
  try {
    await store.deleteProject(props.project.id)
    emit('delete', props.project.id)
  } finally {
    deleting.value = false
  }
}

function formatDate(dateStr: string) {
  return new Date(dateStr).toLocaleDateString(undefined, {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  })
}

const typeLabel = computed(() =>
  props.project.project_type === 'narration' ? 'Narration' : 'Video-to-video',
)

const itemCountLabel = computed(() =>
  props.project.project_type === 'narration'
    ? `${props.project.segment_count ?? 0} segments`
    : `${props.project.cut_count ?? 0} cuts`,
)
</script>

<template>
  <Card class="group transition-shadow hover:shadow-md">
    <CardHeader class="flex flex-row items-start justify-between space-y-0 pb-2">
      <div class="space-y-1">
        <CardTitle class="text-lg">
          <NuxtLink
            :to="`/projects/${project.id}`"
            class="hover:underline"
          >
            {{ project.name }}
          </NuxtLink>
        </CardTitle>
        <CardDescription v-if="project.description">
          {{ project.description }}
        </CardDescription>
        <div class="text-xs uppercase tracking-wide text-muted-foreground">
          {{ typeLabel }}
        </div>
      </div>
      <Button
        variant="ghost"
        size="icon"
        class="h-8 w-8 opacity-0 transition-opacity group-hover:opacity-100"
        :disabled="deleting"
        @click="handleDelete"
      >
        <Trash2 class="h-4 w-4 text-destructive" />
      </Button>
    </CardHeader>
    <CardContent>
      <div class="flex items-center gap-4 text-sm text-muted-foreground">
        <span class="flex items-center gap-1">
          <Film v-if="project.project_type === 'video_to_video'" class="h-4 w-4" />
          <Mic2 v-else class="h-4 w-4" />
          {{ itemCountLabel }}
        </span>
        <span>Created {{ formatDate(project.created_at) }}</span>
      </div>
    </CardContent>
  </Card>
</template>
