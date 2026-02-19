<script setup lang="ts">
const route = useRoute()
const servicesStore = useServicesStore()

const navLinks = [
  { label: 'Home', to: '/' },
  { label: 'Projects', to: '/projects' },
  { label: 'About', to: '/about' },
  { label: 'Admin', to: '/admin' },
]

function isActive(to: string) {
  if (to === '/') return route.path === '/'
  return route.path.startsWith(to)
}

onMounted(() => {
  void servicesStore.fetchHealth()
  servicesStore.startPolling()
})

onUnmounted(() => {
  servicesStore.stopPolling()
})
</script>

<template>
  <div class="flex min-h-screen flex-col bg-background text-foreground">
    <header class="sticky top-0 z-50 w-full border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
      <div class="container mx-auto flex h-14 items-center justify-between px-4">
        <div class="flex items-center gap-6">
          <NuxtLink to="/" class="text-lg font-semibold">
            Inference Club Studio
          </NuxtLink>
          <nav class="flex items-center gap-1">
            <NuxtLink
              v-for="link in navLinks"
              :key="link.to"
              :to="link.to"
              :class="[
                'rounded-md px-3 py-2 text-sm font-medium transition-colors',
                isActive(link.to)
                  ? 'bg-accent text-accent-foreground'
                  : 'text-muted-foreground hover:bg-accent/50 hover:text-accent-foreground',
              ]"
            >
              {{ link.label }}
            </NuxtLink>
          </nav>
        </div>
        <div class="flex items-center gap-2">
          <ServicesNavIndicator />
          <ThemePicker />
        </div>
      </div>
    </header>

    <main class="container mx-auto flex-1 px-4 py-6">
      <slot />
    </main>

    <AppFooter />
  </div>
</template>
