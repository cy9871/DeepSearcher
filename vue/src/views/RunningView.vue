<template>
  <div class="mx-auto max-w-5xl px-6 pt-12 pb-24">
    <!-- Header -->
    <div class="mb-10">
      <div class="flex items-center gap-3">
        <div class="flex items-center gap-2 text-xs font-medium text-accent-600">
          <span class="inline-block h-1.5 w-1.5 rounded-full bg-accent-500 animate-pulse" />
          研究中
        </div>
        <span class="text-xs text-zinc-400">{{ elapsed }}</span>
        <span class="ml-auto text-xs text-zinc-400 tabular-nums">步骤 {{ currentStep }} / {{ maxTurns }}</span>
      </div>
      <h2 class="mt-3 text-lg font-medium tracking-tight text-zinc-800">{{ question }}</h2>
    </div>

    <div class="grid gap-8 md:grid-cols-3">
      <!-- Left + Center: Diary log -->
      <div class="md:col-span-2">
        <div
          ref="logEl"
          class="max-h-[60vh] overflow-y-auto rounded-2xl border border-zinc-200/50 bg-white p-5 shadow-[0_20px_40px_-15px_rgba(0,0,0,0.05)]"
        >
          <div v-if="diary.length === 0" class="flex flex-col items-center justify-center py-16 text-zinc-300">
            <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round">
              <circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/>
            </svg>
            <p class="mt-3 text-sm">等待 Agent 启动...</p>
          </div>
          <div
            v-for="(entry, i) in diary"
            :key="i"
            class="diary-entry py-1.5 text-sm leading-relaxed text-zinc-600 border-b border-zinc-100 last:border-0"
          >
            <span class="font-mono text-xs text-zinc-400 tabular-nums">{{ i + 1 }}.</span>
            {{ entry }}
          </div>
        </div>
      </div>

      <!-- Right: Stats panel -->
      <div>
        <div class="rounded-2xl border border-zinc-200/50 bg-white p-5 shadow-[0_20px_40px_-15px_rgba(0,0,0,0.05)] space-y-5">
          <!-- Stats -->
          <div class="grid grid-cols-2 gap-3">
            <div class="rounded-xl bg-zinc-50 p-3">
              <p class="text-xs text-zinc-400">已读 URL</p>
              <p class="mt-0.5 text-xl font-semibold tabular-nums text-accent-600">{{ visitedCount }}</p>
            </div>
            <div class="rounded-xl bg-zinc-50 p-3">
              <p class="text-xs text-zinc-400">知识条</p>
              <p class="mt-0.5 text-xl font-semibold tabular-nums text-accent-600">{{ knowledgeCount }}</p>
            </div>
            <div class="rounded-xl bg-zinc-50 p-3">
              <p class="text-xs text-zinc-400">搜索到</p>
              <p class="mt-0.5 text-xl font-semibold tabular-nums text-zinc-600">{{ urlCount }}</p>
            </div>
            <div class="rounded-xl bg-zinc-50 p-3">
              <p class="text-xs text-zinc-400">步骤</p>
              <p class="mt-0.5 text-xl font-semibold tabular-nums text-zinc-600">{{ currentStep }}</p>
            </div>
          </div>

          <!-- Progress bar -->
          <div>
            <div class="flex items-center justify-between text-xs text-zinc-400 mb-1.5">
              <span>研究进度</span>
              <span class="tabular-nums">{{ progressPct }}%</span>
            </div>
            <div class="h-1.5 rounded-full bg-zinc-100 overflow-hidden">
              <div
                class="h-full rounded-full bg-accent-500 transition-all duration-500 ease-out"
                :style="{ width: progressPct + '%' }"
              />
            </div>
          </div>

          <!-- Cancel button -->
          <button
            @click="cancelSearch"
            class="w-full rounded-xl border border-zinc-200 px-4 py-2.5 text-xs font-medium text-zinc-500 transition-colors hover:bg-zinc-50 hover:text-zinc-700 active:scale-[0.98]"
          >
            取消
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, nextTick, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { connectSSE, getResult } from '../api/search.js'

const route = useRoute()
const router = useRouter()
const taskId = route.params.taskId

const question = ref('')
const maxTurns = ref(5)
const diary = ref([])
const currentStep = ref(0)
const knowledgeCount = ref(0)
const urlCount = ref(0)
const visitedCount = ref(0)
const elapsed = ref('00:00')
const startTime = Date.now()
const logEl = ref(null)

const progressPct = computed(() => {
  if (!maxTurns.value) return 0
  return Math.min(Math.round((currentStep.value / maxTurns.value) * 100), 95)
})

let timer = null
let cleanup = null

function cancelSearch() {
  cleanup?.()
  router.push({ name: 'input' })
}

onMounted(() => {
  timer = setInterval(() => {
    const s = Math.floor((Date.now() - startTime) / 1000)
    const m = String(Math.floor(s / 60)).padStart(2, '0')
    const sec = String(s % 60).padStart(2, '0')
    elapsed.value = `${m}:${sec}`
  }, 1000)

  cleanup = connectSSE(
    taskId,
    (data) => {
      if (data.diary) diary.value.push(data.diary)
      if (data.step) currentStep.value = data.step
      if (data.knowledge_count != null) knowledgeCount.value = data.knowledge_count
      if (data.url_count != null) urlCount.value = data.url_count
      if (data.visited_count != null) visitedCount.value = data.visited_count
      nextTick(() => {
        if (logEl.value) logEl.value.scrollTop = logEl.value.scrollHeight
      })
    },
    () => {
      // Error — try polling result
      pollResult()
    },
    async () => {
      // Done — navigate to result page
      await new Promise(r => setTimeout(r, 500))
      router.replace({ name: 'result', params: { taskId } })
    }
  )
})

async function pollResult() {
  for (let i = 0; i < 10; i++) {
    await new Promise(r => setTimeout(r, 1000))
    try {
      const data = await getResult(taskId)
      if (data.done) {
        router.replace({ name: 'result', params: { taskId } })
        return
      }
    } catch { /* retry */ }
  }
}

onUnmounted(() => {
  cleanup?.()
  clearInterval(timer)
})
</script>
