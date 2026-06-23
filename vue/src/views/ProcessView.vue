<template>
  <div class="mx-auto max-w-4xl px-6 py-8">
    <!-- Loading -->
    <div v-if="loading" class="text-sm text-zinc-400 py-8 text-center">加载中...</div>

    <!-- Error -->
    <div v-else-if="error" class="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-600">
      {{ error }}
    </div>

    <!-- Content -->
    <div v-else>
      <div class="mb-6">
        <router-link
          to="/history"
          class="inline-flex items-center gap-1 text-xs text-zinc-400 hover:text-zinc-600 transition-colors"
        >
          &larr; 返回历史
        </router-link>
      </div>

      <div class="rounded-lg border border-zinc-200 bg-white p-6">
        <!-- 标题区 -->
        <div class="mb-6 pb-4 border-b border-zinc-100">
          <h1 v-if="title" class="text-lg font-semibold text-zinc-800">{{ title }}</h1>
          <p v-if="meta" class="mt-1 text-xs text-zinc-400">{{ meta }}</p>
        </div>

        <!-- 过程日志渲染 -->
        <div
          class="prose prose-zinc prose-sm max-w-none
                 prose-headings:text-zinc-700 prose-headings:font-medium
                 prose-code:rounded prose-code:bg-zinc-50 prose-code:px-1.5 prose-code:py-0.5 prose-code:text-xs
                 prose-pre:bg-zinc-50 prose-pre:border prose-pre:border-zinc-200"
          v-html="renderedContent"
        />
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { fetchProcessLog } from '../api/search.js'

const route = useRoute()
const taskId = route.params.taskId

const content = ref('')
const loading = ref(true)
const error = ref(null)

const title = computed(() => {
  const lines = content.value.split('\n')
  for (const l of lines) {
    if (l.startsWith('**问题**')) return l.replace('**问题**: ', '').trim()
  }
  return '过程日志'
})

const meta = computed(() => {
  const lines = content.value.split('\n')
  for (const l of lines) {
    if (l.startsWith('**时间**')) return l.replace('**时间**: ', '').trim()
  }
  return ''
})

const renderedContent = computed(() => {
  // 简单 Markdown 转 HTML
  let html = content.value
    // 标题
    .replace(/^### (.+)$/gm, '<h3>$1</h3>')
    .replace(/^## (.+)$/gm, '<h2>$1</h2>')
    .replace(/^# (.+)$/gm, '<h1>$1</h1>')
    // 加粗
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    // 无序列表
    .replace(/^- (.+)$/gm, '<li>$1</li>')
    .replace(/(<li>.*<\/li>\n?)+/g, '<ul>$&</ul>')
    // 换行转段落
    .replace(/\n\n/g, '</p><p>')
    .replace(/^(?!<[hul])/m, '<p>')
    .replace(/(<\/?[hul]|<\/p>)/g, '$1')
  return '<p>' + html + '</p>'
})

onMounted(async () => {
  try {
    const data = await fetchProcessLog(taskId)
    content.value = data.content
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
})
</script>
