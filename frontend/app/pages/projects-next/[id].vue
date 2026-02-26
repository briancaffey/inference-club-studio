<script setup lang="ts">
const route = useRoute()
const store = useProjectsStore()

const projectId = computed(() => route.params.id as string)

const isNarrationProject = computed(() => (
  store.currentProject?.project_type === 'narration'
))

watch(
  () => projectId.value,
  id => {
    if (!id) return
    void store.fetchProject(id)
  },
  { immediate: true },
)

onUnmounted(() => {
  store.currentProject = null
})
</script>

<template>
  <div class="space-y-6">
    <header class="flex items-start justify-between gap-3">
      <div>
        <h1 class="text-2xl font-bold tracking-tight">{{ store.currentProject?.name || 'Projects Next' }}</h1>
        <p class="text-sm text-muted-foreground">Modular narration workspace preview.</p>
      </div>

      <div class="flex gap-2">
        <NuxtLink to="/projects-next" class="rounded-md border px-3 py-1.5 text-sm hover:bg-muted">
          All Next Projects
        </NuxtLink>
        <NuxtLink :to="`/projects/${projectId}`" class="rounded-md border px-3 py-1.5 text-sm hover:bg-muted">
          Legacy View
        </NuxtLink>
      </div>
    </header>

    <div v-if="store.loading && !store.currentProject" class="rounded-xl border border-dashed p-8 text-center text-sm text-muted-foreground">
      Loading project...
    </div>

    <div v-else-if="store.currentProject && !isNarrationProject" class="rounded-xl border border-dashed p-8 text-center text-sm text-muted-foreground">
      This project is not a narration project.
    </div>

    <NarrationWorkspaceNext v-else-if="store.currentProject" :project-id="projectId" />
  </div>
</template>
