<script setup lang="ts">
import { Settings, ExternalLink } from 'lucide-vue-next'
</script>

<template>
  <div>
    <PageHeader
      title="Admin"
      description="Manage your Inference Club Studio instance."
    />

    <div class="grid gap-6 sm:grid-cols-2">
      <Card>
        <CardHeader>
          <CardTitle class="flex items-center gap-2">
            <Settings class="h-5 w-5" />
            General Settings
          </CardTitle>
          <CardDescription>
            Configure your instance settings and preferences.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <p class="text-sm text-muted-foreground">
            Settings panel coming soon. This is where you'll manage models, API keys, and instance configuration.
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Quick Links</CardTitle>
          <CardDescription>
            Helpful resources and navigation.
          </CardDescription>
        </CardHeader>
        <CardContent class="flex flex-col gap-3">
          <Button variant="outline" as-child class="justify-start">
            <NuxtLink to="/about">
              <ExternalLink class="mr-2 h-4 w-4" />
              About Inference Club Studio
            </NuxtLink>
          </Button>
        </CardContent>
      </Card>
    </div>
  </div>
</template>
