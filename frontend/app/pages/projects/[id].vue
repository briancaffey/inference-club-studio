<script setup lang="ts">
import { ArrowLeft, Pencil, Check, X } from 'lucide-vue-next'
import type { Cut } from '~/types'

const route = useRoute()
const store = useProjectsStore()

const projectId = route.params.id as string
const previewCut = ref<Cut | null>(null)
const previewOpen = ref(false)
const editing = ref(false)
const editName = ref('')
const editDescription = ref('')

// Fetch project
onMounted(() => {
  store.fetchProject(projectId)
})

// Poll while any cut is still processing
const pollInterval = ref<ReturnType<typeof setInterval>>()

const hasProcessingCuts = computed(() =>
  store.currentProject?.cuts?.some(c =>
    ['uploaded', 'processing_metadata', 'extracting_audio'].includes(c.status),
  ),
)

watch(hasProcessingCuts, (processing) => {
  if (processing && !pollInterval.value) {
    pollInterval.value = setInterval(() => {
      store.fetchProject(projectId)
    }, 3000)
  } else if (!processing && pollInterval.value) {
    clearInterval(pollInterval.value)
    pollInterval.value = undefined
  }
})

onUnmounted(() => {
  if (pollInterval.value) clearInterval(pollInterval.value)
  store.currentProject = null
})

function openPreview(cut: Cut) {
  previewCut.value = cut
  previewOpen.value = true
}

async function handleReorder(cutIds: string[]) {
  await store.reorderCuts(projectId, cutIds)
}

function startEditing() {
  if (!store.currentProject) return
  editName.value = store.currentProject.name
  editDescription.value = store.currentProject.description || ''
  editing.value = true
}

async function saveEdit() {
  await store.updateProject(projectId, {
    name: editName.value,
    description: editDescription.value || undefined,
  })
  editing.value = false
}
</script>

<template>
  <div class="space-y-6">
    <div class="flex items-center gap-2">
      <Button variant="ghost" size="icon" as-child>
        <NuxtLink to="/projects">
          <ArrowLeft class="h-4 w-4" />
        </NuxtLink>
      </Button>

      <template v-if="!editing && store.currentProject">
        <div class="flex-1">
          <h1 class="text-2xl font-bold">{{ store.currentProject.name }}</h1>
          <p v-if="store.currentProject.description" class="text-sm text-muted-foreground">
            {{ store.currentProject.description }}
          </p>
        </div>
        <Button variant="ghost" size="icon" @click="startEditing">
          <Pencil class="h-4 w-4" />
        </Button>
      </template>

      <template v-if="editing">
        <div class="flex flex-1 items-center gap-2">
          <Input v-model="editName" class="max-w-xs" />
          <Input v-model="editDescription" placeholder="Description" class="max-w-sm" />
          <Button size="icon" variant="ghost" @click="saveEdit">
            <Check class="h-4 w-4" />
          </Button>
          <Button size="icon" variant="ghost" @click="editing = false">
            <X class="h-4 w-4" />
          </Button>
        </div>
      </template>
    </div>

    <div v-if="store.loading && !store.currentProject" class="flex justify-center py-12">
      <Spinner class="h-8 w-8" />
    </div>

    <template v-else-if="store.currentProject">
      <CutUploadZone :project-id="projectId" />

      <div v-if="!store.currentProject.cuts?.length" class="py-8 text-center">
        <p class="text-muted-foreground">No cuts yet. Upload video files above.</p>
      </div>

      <CutList
        v-else
        :cuts="store.currentProject.cuts"
        :project-id="projectId"
        @preview="openPreview"
        @reorder="handleReorder"
      />
    </template>

    <VideoPreviewDialog
      v-model:open="previewOpen"
      :cut="previewCut"
    />
  </div>
</template>
