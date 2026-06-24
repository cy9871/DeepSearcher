<template>
  <div class="min-h-[100dvh] flex flex-col">
    <!-- Nav -->
    <header class="border-b border-zinc-200/50 bg-white/80 backdrop-blur-sm sticky top-0 z-10">
      <div class="mx-auto flex max-w-6xl items-center justify-between px-6 py-3">
          <router-link to="/" class="flex items-center gap-2 text-sm font-medium text-zinc-600 hover:text-zinc-900 transition-colors">
            <svg width="20" height="20" viewBox="0 0 32 32" fill="none">
              <circle cx="16" cy="16" r="14" stroke="currentColor" stroke-width="2"/>
              <path d="M10 16 L14 20 L22 12" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
            Deep Research
          </router-link>
          <nav class="flex items-center gap-4">
            <router-link to="/history" class="text-xs text-zinc-400 hover:text-zinc-600 transition-colors">历史</router-link>
            <router-link to="/eval" class="text-xs text-zinc-400 hover:text-zinc-600 transition-colors">评估</router-link>
          </nav>
        <span class="text-xs text-zinc-400">深度研究 Agent</span>
      </div>
    </header>

    <!-- Main -->
    <main class="flex-1">
      <router-view />
    </main>
  </div>
</template>

<script setup>
</script>
