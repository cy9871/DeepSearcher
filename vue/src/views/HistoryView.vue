<template>
  <div class="mx-auto max-w-4xl px-6 py-8">
    <h1 class="text-xl font-semibold text-zinc-800 mb-6">研究历史</h1>

    <!-- Loading -->
    <div v-if="loading" class="text-sm text-zinc-400 py-8 text-center">加载中...</div>

    <!-- Error -->
    <div v-else-if="error" class="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-600">
      {{ error }}
    </div>

    <!-- Empty -->
    <div v-else-if="tasks.length === 0" class="text-sm text-zinc-400 py-12 text-center">
      还没有研究记录。去<a href="/" class="text-emerald-600 hover:text-emerald-700 underline ml-1">首页</a>开始研究吧。
    </div>

    <!-- Task list -->
    <div v-else class="space-y-3">
      <div
        v-for="t in sortedTasks"
        :key="t.task_id"
        class="rounded-lg border border-zinc-200 bg-white px-5 py-4 hover:border-emerald-300 transition-colors cursor-pointer"
        @click="viewResult(t.task_id)"
      >
        <div class="flex items-start justify-between gap-4">
          <div class="min-w-0 flex-1">
            <h3 class="text-sm font-medium text-zinc-800 truncate">{{ t.question }}</h3>
            <div class="mt-1.5 flex flex-wrap items-center gap-3 text-xs text-zinc-400">
              <span>{{ t.created_str }}</span>
              <span>{{ t.steps }} 步</span>
              <span>{{ t.knowledge_count }} 条知识</span>
              <span>{{ t.ref_count }} 个引用</span>
            </div>
          </div>
          <div class="flex items-center gap-2 shrink-0">
            <span
              class="inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium"
              :class="t.beast_mode_used ? 'bg-amber-50 text-amber-600' : 'bg-emerald-50 text-emerald-600'"
            >
              {{ t.beast_mode_used ? 'Beast' : '正常' }}
            </span>
            <button
              class="rounded-md px-2.5 py-1 text-xs text-zinc-500 hover:text-zinc-700 hover:bg-zinc-100 transition-colors"
              @click.stop="viewProcess(t.task_id)"
            >
              过程
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { fetchHistory } from '../api/search.js'

const router = useRouter()
const tasks = ref([])
const loading = ref(true)
const error = ref(null)

const sortedTasks = computed(() =>
  [...tasks.value].sort((a, b) => b.created_at - a.created_at)
)

onMounted(async () => {
  try {
    tasks.value = await fetchHistory()
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
})

function viewResult(taskId) {
  router.push(`/result/${taskId}`)
}

function viewProcess(taskId) {
  router.push(`/process/${taskId}`)
}
</script>
