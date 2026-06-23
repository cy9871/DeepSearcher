<template>
  <div class="mx-auto max-w-4xl px-6 pt-12 pb-24">
    <!-- Back -->
    <button
      @click="$router.push({ name: 'input' })"
      class="group mb-8 flex items-center gap-1.5 text-sm text-zinc-400 hover:text-zinc-600 transition-colors"
    >
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="transition-transform group-hover:-translate-x-0.5">
        <path d="m15 18-6-6 6-6"/>
      </svg>
      新研究
    </button>

    <!-- Question -->
    <h1 class="text-2xl font-semibold tracking-tight text-zinc-900 leading-tight">{{ question }}</h1>

    <!-- Stats bar -->
    <div class="mt-4 flex flex-wrap items-center gap-3 text-xs text-zinc-400">
      <span class="tabular-nums">{{ steps }} 步骤</span>
      <span class="h-3 w-px bg-zinc-200"/>
      <span class="tabular-nums">{{ knowledgeCount }} 条知识</span>
      <span class="h-3 w-px bg-zinc-200"/>
      <span class="tabular-nums" :class="refCount > 0 ? 'text-accent-600' : ''">{{ refCount }} 个引用</span>
      <span v-if="beastMode" class="ml-auto rounded-full bg-amber-50 px-2.5 py-0.5 text-amber-600">Beast Mode</span>
    </div>

    <!-- Answer -->
    <div class="mt-8 rounded-2xl border border-zinc-200/50 bg-white p-8 shadow-[0_20px_40px_-15px_rgba(0,0,0,0.05)]">
      <div v-if="!answer" class="flex flex-col items-center justify-center py-20 text-zinc-300">
        <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round">
          <circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/>
        </svg>
        <p class="mt-3 text-sm">加载中...</p>
      </div>
      <div
        v-else
        class="prose-answer"
        v-html="renderedAnswer"
      />
    </div>

    <!-- References -->
    <div v-if="references.length > 0" class="mt-8">
      <h2 class="text-sm font-medium text-zinc-700 mb-3">引用来源</h2>
      <div class="space-y-2">
        <a
          v-for="(ref, i) in references"
          :key="i"
          :href="ref"
          target="_blank"
          rel="noopener noreferrer"
          class="flex items-start gap-2 rounded-xl border border-zinc-200/50 bg-white px-4 py-3 text-xs text-zinc-500 hover:border-accent-200 hover:text-accent-600 transition-colors"
        >
          <span class="mt-0.5 shrink-0 font-mono text-zinc-300">{{ i + 1 }}.</span>
          <span class="break-all">{{ ref }}</span>
          <svg class="mt-0.5 ml-auto shrink-0 h-3 w-3 opacity-40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/>
          </svg>
        </a>
      </div>
    </div>

    <!-- Error -->
    <div v-if="error" class="mt-8 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-600">
      {{ error }}
    </div>

    <!-- CTA -->
    <div class="mt-12 text-center">
      <button
        @click="$router.push({ name: 'input' })"
        class="inline-flex items-center gap-2 rounded-xl bg-accent-500 px-6 py-3 text-sm font-medium text-white transition-all hover:bg-accent-600 active:scale-[0.98]"
      >
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/>
        </svg>
        再来一次
      </button>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, computed } from 'vue'
import { useRoute } from 'vue-router'
import { getResult } from '../api/search.js'
import { marked } from 'marked'

const route = useRoute()
const taskId = route.params.taskId

const question = ref('')
const answer = ref('')
const references = ref([])
const steps = ref(0)
const knowledgeCount = ref(0)
const beastMode = ref(false)
const error = ref('')

const refCount = computed(() => references.value.length)

const renderedAnswer = computed(() => {
  if (!answer.value) return ''
  return marked(answer.value)
})

onMounted(async () => {
  try {
    const data = await getResult(taskId)
    if (data.error) {
      error.value = data.error
      return
    }
    const r = data.result
    question.value = r.answer.split('\n')[0]?.slice(0, 60) || '研究结果'
    answer.value = r.answer
    references.value = r.references || []
    steps.value = r.steps || 0
    knowledgeCount.value = r.knowledge_count || 0
    beastMode.value = r.beast_mode_used || false
  } catch (e) {
    error.value = '获取结果失败: ' + (e.message || '')
  }
})
</script>
