<template>
  <div class="mx-auto max-w-5xl px-6 pt-16 pb-24">
    <div class="grid gap-12 md:grid-cols-5">
      <!-- Left: Branding -->
      <div class="md:col-span-2 md:pt-4">
        <h1 class="text-4xl font-semibold tracking-tighter text-zinc-900 leading-none">
          深度研究
        </h1>
        <p class="mt-4 text-sm leading-relaxed text-zinc-500 max-w-[40ch]">
          输入一个问题，Agent 会自主搜索、阅读、反思，最终生成带引用的研究报告。
        </p>
        <div class="mt-8 flex flex-wrap gap-1.5 text-xs text-zinc-400">
          <span class="rounded-full border border-zinc-200 px-3 py-1">DuckDuckGo 搜索</span>
          <span class="rounded-full border border-zinc-200 px-3 py-1">网页阅读</span>
          <span class="rounded-full border border-zinc-200 px-3 py-1">质量门禁</span>
          <span class="rounded-full border border-zinc-200 px-3 py-1">Beast Mode 兜底</span>
        </div>
      </div>

      <!-- Right: Form -->
      <div class="md:col-span-3">
        <div class="rounded-2xl border border-zinc-200/50 bg-white p-8 shadow-[0_20px_40px_-15px_rgba(0,0,0,0.05)]">
          <form @submit.prevent="handleSubmit" class="space-y-6">
            <!-- Question -->
            <div>
              <label class="mb-2 block text-sm font-medium text-zinc-700">研究问题</label>
              <textarea
                v-model="question"
                rows="4"
                placeholder="例如：LangGraph 和 CrewAI 的设计哲学差异"
                class="w-full resize-none rounded-xl border border-zinc-200 bg-zinc-50/50 px-4 py-3 text-sm text-zinc-900 placeholder:text-zinc-400 focus:border-accent-400 focus:outline-none focus:ring-2 focus:ring-accent-100 transition-colors"
                @keydown.enter.ctrl="handleSubmit"
              />
              <p class="mt-1.5 text-xs text-zinc-400">Ctrl + Enter 快捷提交</p>
            </div>

            <!-- Max turns -->
            <div>
              <label class="mb-2 block text-sm font-medium text-zinc-700">研究深度</label>
              <div class="flex items-center gap-4">
                <input
                  v-model.number="maxTurns"
                  type="range"
                  min="1"
                  max="5"
                  class="flex-1 h-1.5 appearance-none rounded-full bg-zinc-200 accent-accent-500 cursor-pointer"
                />
                <span class="min-w-[4rem] text-right text-sm tabular-nums text-zinc-500">
                  {{ maxTurns }} 轮
                </span>
              </div>
              <p class="mt-1 text-xs text-zinc-400">
                {{ maxTurns <= 2 ? '快速回答' : '深度研究' }}
              </p>
            </div>

            <!-- Submit -->
            <button
              type="submit"
              :disabled="!question.trim() || loading"
              class="flex w-full items-center justify-center gap-2 rounded-xl bg-accent-500 px-6 py-3 text-sm font-medium text-white transition-all hover:bg-accent-600 active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-40"
            >
              <svg v-if="loading" class="h-4 w-4 animate-spin" viewBox="0 0 24 24" fill="none">
                <circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="3" stroke-linecap="round" class="opacity-30"/>
                <path d="M12 2 A10 10 0 0 1 22 12" stroke="currentColor" stroke-width="3" stroke-linecap="round"/>
              </svg>
              <svg v-else width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/>
              </svg>
              {{ loading ? '启动中...' : '开始研究' }}
            </button>
          </form>

          <!-- Error -->
          <div v-if="error" class="mt-4 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-600">
            {{ error }}
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { startSearch } from '../api/search.js'

const router = useRouter()
const question = ref('')
const maxTurns = ref(3)
const loading = ref(false)
const error = ref('')

async function handleSubmit() {
  if (!question.value.trim() || loading.value) return
  loading.value = true
  error.value = ''

  try {
    const data = await startSearch(question.value, maxTurns.value)
    router.push({ name: 'running', params: { taskId: data.task_id } })
  } catch (e) {
    error.value = e.message || '请求失败，请检查后端是否运行'
  } finally {
    loading.value = false
  }
}
</script>
