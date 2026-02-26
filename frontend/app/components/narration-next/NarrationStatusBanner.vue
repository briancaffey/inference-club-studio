<script setup lang="ts">
defineProps<{
  status: string
  error: string | null
  generating: boolean
  genEstimate: number | null
  genProgress: number
}>()
</script>

<template>
  <section
    v-if="status"
    data-testid="status-banner"
    class="rounded-xl border px-3 py-2 text-sm"
    :class="error ? 'border-red-300 bg-red-50 text-red-700 dark:border-red-900 dark:bg-red-950/30 dark:text-red-200' : 'border-sky-300 bg-sky-50 text-sky-700 dark:border-sky-900 dark:bg-sky-950/30 dark:text-sky-200'"
  >
    <div class="flex items-center gap-2">
      <span class="font-medium">{{ status }}</span>
      <span v-if="genEstimate" class="ml-auto text-xs opacity-75">~{{ genEstimate }}s</span>
    </div>

    <div v-if="generating" class="mt-2 h-1.5 overflow-hidden rounded-full bg-sky-200/80 dark:bg-sky-900/60">
      <div
        data-testid="generation-progress"
        class="h-full rounded-full bg-sky-500 transition-all duration-300"
        :style="{ width: `${genProgress}%` }"
      />
    </div>
  </section>
</template>
