<template>
  <div class="min-h-screen bg-background text-foreground">
    <header class="sticky top-0 z-50 w-full border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
      <div class="container flex h-14 items-center justify-between px-4">
        <div class="flex items-center gap-4">
          <NuxtLink to="/" class="text-lg font-semibold">
            Inference Club
          </NuxtLink>
        </div>
        <div class="flex items-center gap-2">
          <ThemePicker />
        </div>
      </div>
    </header>
    <main class="container px-4 py-6">
      <slot />
    </main>
  </div>
</template>
