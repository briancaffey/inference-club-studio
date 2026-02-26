<script setup lang="ts">
const store = useProjectsStore()

const narrationProjects = computed(() => (
  store.projects.filter(project => project.project_type === 'narration')
))

onMounted(() => {
  void store.fetchProjects()
})
</script>

<template>
  <div class="space-y-6">
    <header class="flex items-center justify-between gap-3">
      <div>
        <h1 class="text-2xl font-bold tracking-tight">Projects Next</h1>
        <p class="text-sm text-muted-foreground">Narration projects using the modular workspace.</p>
      </div>
      <NuxtLink to="/projects" class="rounded-md border px-3 py-1.5 text-sm hover:bg-muted">
        Back to Projects
      </NuxtLink>
    </header>

    <div v-if="store.loading" class="rounded-xl border border-dashed p-8 text-center text-sm text-muted-foreground">
      Loading narration projects...
    </div>

    <div v-else-if="!narrationProjects.length" class="rounded-xl border border-dashed p-8 text-center text-sm text-muted-foreground">
      No narration projects found.
    </div>

    <div v-else class="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
      <NuxtLink
        v-for="project in narrationProjects"
        :key="project.id"
        :to="`/projects-next/${project.id}`"
        class="rounded-xl border border-border/70 bg-card p-4 transition hover:border-primary/40 hover:shadow-sm"
      >
        <p class="text-sm font-semibold">{{ project.name }}</p>
        <p class="mt-1 text-xs text-muted-foreground">{{ project.description || 'No description' }}</p>
        <p class="mt-3 text-[11px] uppercase tracking-wide text-muted-foreground">Open workspace</p>
      </NuxtLink>
    </div>
  </div>
</template>
