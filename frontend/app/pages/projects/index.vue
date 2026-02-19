<script setup lang="ts">
const store = useProjectsStore()

onMounted(() => {
  store.fetchProjects()
})
</script>

<template>
  <div class="space-y-6">
    <div class="flex items-center justify-between">
      <PageHeader
        title="Projects"
        description="Manage narration and video-to-video projects"
      />
      <CreateProjectDialog />
    </div>

    <div v-if="store.loading" class="flex justify-center py-12">
      <Spinner class="h-8 w-8" />
    </div>

    <div v-else-if="store.projects.length === 0" class="py-12 text-center">
      <p class="text-muted-foreground">No projects yet. Create one to get started.</p>
    </div>

    <div v-else class="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      <ProjectCard
        v-for="project in store.projects"
        :key="project.id"
        :project="project"
      />
    </div>
  </div>
</template>
