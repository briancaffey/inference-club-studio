<script setup lang="ts">
import { ArrowLeft, Pencil, Check, X } from 'lucide-vue-next'
import type { Cut } from '~/types'

const route = useRoute()
const store = useProjectsStore()
const generationsStore = useGenerationsStore()
const takesStore = useTakesStore()

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
const cutPollInterval = ref<ReturnType<typeof setInterval>>()

const hasProcessingCuts = computed(() =>
  store.currentProject?.cuts?.some(c =>
    ['uploaded', 'processing_metadata', 'extracting_audio'].includes(c.status),
  ),
)

watch(hasProcessingCuts, (processing) => {
  if (processing && !cutPollInterval.value) {
    cutPollInterval.value = setInterval(() => {
      store.fetchProject(projectId)
    }, 3000)
  } else if (!processing && cutPollInterval.value) {
    clearInterval(cutPollInterval.value)
    cutPollInterval.value = undefined
  }
})

// Poll generations while any are in-progress
const genPollInterval = ref<ReturnType<typeof setInterval>>()

const hasActiveGenerations = computed(() => {
  const cuts = store.currentProject?.cuts || []
  return cuts.some(c => generationsStore.hasActiveGenerations(c.id))
})

watch(hasActiveGenerations, (active) => {
  if (active && !genPollInterval.value) {
    genPollInterval.value = setInterval(() => {
      const cuts = store.currentProject?.cuts || []
      for (const cut of cuts) {
        if (generationsStore.hasActiveGenerations(cut.id)) {
          generationsStore.fetchGenerations(projectId, cut.id)
        }
      }
    }, 3000)
  } else if (!active && genPollInterval.value) {
    clearInterval(genPollInterval.value)
    genPollInterval.value = undefined
  }
})

// Poll takes while any are in-progress
const takePollInterval = ref<ReturnType<typeof setInterval>>()

const hasActiveTakes = computed(() => {
  const allGenerationIds = Object.keys(takesStore.takes)
  return allGenerationIds.some(gid => takesStore.hasActiveTakes(gid))
})

watch(hasActiveTakes, (active) => {
  if (active && !takePollInterval.value) {
    takePollInterval.value = setInterval(() => {
      const cuts = store.currentProject?.cuts || []
      for (const cut of cuts) {
        const gens = generationsStore.generationsForCut(cut.id)
        for (const gen of gens) {
          if (takesStore.hasActiveTakes(gen.id)) {
            takesStore.fetchTakes(projectId, cut.id, gen.id)
          }
        }
      }
    }, 3000)
  } else if (!active && takePollInterval.value) {
    clearInterval(takePollInterval.value)
    takePollInterval.value = undefined
  }
})

onUnmounted(() => {
  if (cutPollInterval.value) clearInterval(cutPollInterval.value)
  if (genPollInterval.value) clearInterval(genPollInterval.value)
  if (takePollInterval.value) clearInterval(takePollInterval.value)
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
      :project-id="projectId"
      :cut="previewCut"
    />
  </div>
</template>
