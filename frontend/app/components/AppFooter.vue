<script setup lang="ts">
import { Github } from 'lucide-vue-next'

const currentYear = new Date().getFullYear()

const footerLinks = {
  product: [
    { label: 'Home', to: '/' },
    { label: 'About', to: '/about' },
    { label: 'Admin', to: '/admin' },
  ],
  resources: [
    { label: 'Documentation', to: '#' },
    { label: 'Changelog', to: '#' },
    { label: 'Support', to: '#' },
  ],
}
</script>

<template>
  <footer class="border-t bg-muted/40">
    <div class="container mx-auto px-4 py-12">
      <div class="grid grid-cols-1 gap-8 sm:grid-cols-2 lg:grid-cols-4">
        <div class="sm:col-span-2 lg:col-span-2">
          <NuxtLink to="/" class="text-lg font-semibold">
            Inference Club Studio
          </NuxtLink>
          <p class="mt-2 max-w-sm text-sm text-muted-foreground">
            Build, experiment, and explore with AI inference tools. A collaborative studio for the curious.
          </p>
          <div class="mt-4 flex items-center gap-3">
            <Button variant="ghost" size="icon" as="a" href="#" aria-label="GitHub">
              <Github class="h-5 w-5" />
            </Button>
          </div>
        </div>

        <div>
          <h3 class="text-sm font-semibold">Product</h3>
          <ul class="mt-3 space-y-2">
            <li v-for="link in footerLinks.product" :key="link.to">
              <NuxtLink :to="link.to" class="text-sm text-muted-foreground transition-colors hover:text-foreground">
                {{ link.label }}
              </NuxtLink>
            </li>
          </ul>
        </div>

        <div>
          <h3 class="text-sm font-semibold">Resources</h3>
          <ul class="mt-3 space-y-2">
            <li v-for="link in footerLinks.resources" :key="link.label">
              <NuxtLink :to="link.to" class="text-sm text-muted-foreground transition-colors hover:text-foreground">
                {{ link.label }}
              </NuxtLink>
            </li>
          </ul>
        </div>
      </div>

      <Separator class="my-8" />

      <div class="flex flex-col items-center justify-between gap-4 sm:flex-row">
        <p class="text-sm text-muted-foreground">
          &copy; {{ currentYear }} Inference Club Studio. All rights reserved.
        </p>
        <div class="flex gap-4">
          <NuxtLink to="#" class="text-sm text-muted-foreground transition-colors hover:text-foreground">
            Privacy
          </NuxtLink>
          <NuxtLink to="#" class="text-sm text-muted-foreground transition-colors hover:text-foreground">
            Terms
          </NuxtLink>
        </div>
      </div>
    </div>
  </footer>
</template>
