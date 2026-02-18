<script setup lang="ts">
import { ArrowRight, Sparkles } from 'lucide-vue-next'
</script>

<template>
  <div>
    <section class="flex flex-col items-center justify-center py-24 text-center">
      <Badge variant="secondary" class="mb-4">
        <Sparkles class="mr-1 h-3 w-3" />
        Now in early access
      </Badge>
      <h1 class="max-w-3xl text-5xl font-bold tracking-tight sm:text-6xl">
        Build and explore AI inference together
      </h1>
      <p class="mt-6 max-w-2xl text-lg text-muted-foreground">
        Inference Club Studio is a collaborative workspace for experimenting with AI models,
        sharing results, and learning from each other. Jump in and start building.
      </p>
      <div class="mt-10 flex flex-wrap items-center justify-center gap-4">
        <Button size="lg" as-child>
          <NuxtLink to="/about">
            Get started
            <ArrowRight class="ml-2 h-4 w-4" />
          </NuxtLink>
        </Button>
        <Button size="lg" variant="outline" as-child>
          <NuxtLink to="/admin">
            Go to Admin
          </NuxtLink>
        </Button>
      </div>
    </section>

    <Separator />

    <section class="py-16">
      <div class="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
        <Card>
          <CardHeader>
            <CardTitle>Experiment</CardTitle>
            <CardDescription>
              Run inference jobs against multiple models and compare results side by side.
            </CardDescription>
          </CardHeader>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Collaborate</CardTitle>
            <CardDescription>
              Share your experiments with the club and build on each other's work.
            </CardDescription>
          </CardHeader>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Learn</CardTitle>
            <CardDescription>
              Explore how different prompts, parameters, and models affect outputs.
            </CardDescription>
          </CardHeader>
        </Card>
      </div>
    </section>
  </div>
</template>
