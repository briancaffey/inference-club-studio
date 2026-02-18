<script setup lang="ts">
defineProps<{
  title: string
  description?: string
}>()
</script>

<template>
  <div class="pb-8">
    <h1 class="text-3xl font-bold tracking-tight">
      {{ title }}
    </h1>
    <p v-if="description" class="mt-2 text-lg text-muted-foreground">
      {{ description }}
    </p>
  </div>
</template>
