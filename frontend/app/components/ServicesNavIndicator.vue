<script setup lang="ts">
import { storeToRefs } from 'pinia'
import { CheckCircle2, Loader2, XCircle } from 'lucide-vue-next'

const servicesStore = useServicesStore()
const {
  allHealthy,
  degradedCount,
  error,
  healthyServices,
  loading,
  totalServices,
} = storeToRefs(servicesStore)

const hasResults = computed(() => totalServices.value > 0)

const statusLabel = computed(() => {
  if (loading.value && !hasResults.value) return 'Checking services...'
  if (!hasResults.value && error.value) return 'Unable to load services'
  if (!hasResults.value) return 'Services unknown'
  if (allHealthy.value) return 'All services healthy'
  const noun = degradedCount.value === 1 ? 'service' : 'services'
  return `${degradedCount.value} ${noun} unreachable`
})

const countLabel = computed(() =>
  hasResults.value ? `${healthyServices.value}/${totalServices.value}` : '—',
)

const containerClass = computed(() => {
  if (hasResults.value && allHealthy.value) {
    return 'border-emerald-500/40 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300'
  }
  if (hasResults.value || error.value) {
    return 'border-red-500/40 bg-red-500/10 text-red-700 dark:text-red-300'
  }
  return 'border-border bg-muted/40 text-muted-foreground'
})
</script>

<template>
  <NuxtLink
    to="/admin#services"
    :title="statusLabel"
    :class="[
      'inline-flex items-center gap-2 rounded-full border px-2.5 py-1 text-xs font-medium transition-colors',
      containerClass,
    ]"
  >
    <Loader2
      v-if="loading && !hasResults"
      class="h-3.5 w-3.5 animate-spin"
    />
    <CheckCircle2
      v-else-if="hasResults && allHealthy"
      class="h-3.5 w-3.5"
    />
    <XCircle v-else class="h-3.5 w-3.5" />

    <span class="hidden sm:inline">Services</span>
    <span class="font-semibold tabular-nums">{{ countLabel }}</span>
  </NuxtLink>
</template>
