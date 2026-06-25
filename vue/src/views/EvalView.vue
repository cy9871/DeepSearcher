<template>
  <div class="max-w-6xl mx-auto px-6 py-8">
    <!-- 页头 -->
    <div class="mb-8">
      <h1 class="text-2xl font-bold text-zinc-900">📊 Agent 效果评估</h1>
      <p class="text-sm text-zinc-500 mt-1">任务完成率 / 工具准确率 / 路径分析 / 耗时 / 异常监控</p>
    </div>

    <!-- 加载中 -->
    <div v-if="loading" class="flex items-center justify-center py-20 text-zinc-400">
      <svg class="animate-spin h-6 w-6 mr-2" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" fill="none"/><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/></svg>
      加载评估数据...
    </div>

    <!-- 无数据 -->
    <div v-else-if="!summary || summary.total_tasks === 0" class="text-center py-20">
      <div class="text-5xl mb-4">📭</div>
      <p class="text-zinc-600 font-medium">暂无评估数据</p>
      <p class="text-zinc-400 text-sm mt-2">运行一次研究任务后，指标会自动采集。</p>
      <router-link to="/" class="inline-block mt-6 px-5 py-2 bg-zinc-900 text-white text-sm rounded-lg hover:bg-zinc-700 transition">
        开始研究
      </router-link>
    </div>

    <!-- 仪表盘 -->
    <template v-else>
      <!-- 概览卡片 -->
      <div class="grid grid-cols-2 md:grid-cols-5 gap-4 mb-8">
        <StatCard label="任务总数" :value="summary.total_tasks" color="slate" />
        <StatCard label="完成率" :value="fmtPct(tc.completion_rate)" :trend="tc.completion_rate >= 0.7 ? 'up' : 'down'" color="emerald" />
        <StatCard label="门禁通过率" :value="fmtPct(tc.eval_pass_rate)" :trend="tc.eval_pass_rate >= 0.6 ? 'up' : 'down'" color="blue" />
        <StatCard label="Beast Mode" :value="fmtPct(tc.beast_mode_rate)" :trend="tc.beast_mode_rate > 0.3 ? 'up' : 'down'" color="amber" invert />
        <StatCard label="动作失败率" :value="fmtPct(ar.action_failure_rate)" :trend="ar.action_failure_rate > 0.1 ? 'up' : 'down'" color="rose" invert />
      </div>

      <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">

        <!-- 1. 任务完成率详情 -->
        <section class="rounded-xl border border-zinc-200 bg-white p-5">
          <div class="flex items-center justify-between mb-4">
            <h2 class="text-sm font-semibold text-zinc-800">1️⃣ 任务完成率</h2>
            <span class="text-xs text-zinc-400">{{ tc.completed }}/{{ tc.total_tasks }} 完成</span>
          </div>
          <div class="space-y-3">
            <div class="flex items-center gap-3">
              <div class="flex-1 h-8 bg-zinc-100 rounded-full overflow-hidden flex">
                <div class="h-full bg-emerald-500 rounded-l-full transition-all duration-700" :style="{ width: fmtPct(tc.completion_rate) }"></div>
                <div v-if="tc.beast_mode_rate > 0" class="h-full bg-amber-400 transition-all duration-700" :style="{ width: fmtPct(tc.beast_mode_rate) }"></div>
              </div>
              <span class="text-sm text-zinc-600 min-w-[4ch] font-mono">{{ fmtPct(tc.completion_rate) }}</span>
            </div>
            <div class="flex gap-4 text-xs text-zinc-500">
              <span class="flex items-center gap-1"><span class="w-3 h-3 rounded-sm bg-emerald-500 inline-block"></span>完成</span>
              <span v-if="tc.beast_mode_rate > 0" class="flex items-center gap-1"><span class="w-3 h-3 rounded-sm bg-amber-400 inline-block"></span>Beast Mode</span>
            </div>
            <div class="pt-2 grid grid-cols-3 gap-2">
              <MiniRow label="门禁通过" :val="tc.eval_passed" :total="tc.total_tasks" color="emerald" />
              <MiniRow label="Beast 触发" :val="beastCount" :total="tc.total_tasks" color="amber" />
              <MiniRow label="完成" :val="tc.completed" :total="tc.total_tasks" color="blue" />
            </div>
          </div>
        </section>

        <!-- 2. 工具调用准确率 -->
        <section class="rounded-xl border border-zinc-200 bg-white p-5">
          <div class="flex items-center justify-between mb-4">
            <h2 class="text-sm font-semibold text-zinc-800">2️⃣ 工具调用准确率</h2>
            <span class="text-xs text-zinc-400">按动作类型</span>
          </div>
          <div v-if="summary.tool_accuracy.length === 0" class="text-xs text-zinc-400 py-4">暂无数据</div>
          <div v-else class="space-y-2.5">
            <div v-for="ta in summary.tool_accuracy" :key="ta.action_type" class="flex items-center gap-2">
              <span class="text-xs text-zinc-600 w-16 shrink-0 text-right font-mono">{{ ta.action_type }}</span>
              <div class="flex-1 h-6 bg-zinc-100 rounded-full overflow-hidden flex relative">
                <div class="h-full rounded-full transition-all duration-700 absolute left-0 top-0"
                     :class="rateColorClass(ta.success_rate)"
                     :style="{ width: fmtPct(ta.success_rate) }"></div>
              </div>
              <span class="text-xs font-mono w-14 shrink-0" :class="rateTextClass(ta.success_rate)">
                {{ fmtPct(ta.success_rate) }}
              </span>
              <span class="text-xs text-zinc-400 w-16 shrink-0 text-right">{{ ta.successful }}/{{ ta.total }}</span>
            </div>
          </div>
          <!-- 耗时子信息 -->
          <div v-if="summary.tool_accuracy.length > 0" class="mt-4 pt-3 border-t border-zinc-100">
            <div class="text-xs text-zinc-400 mb-2">平均耗时</div>
            <div class="flex flex-wrap gap-2">
              <span v-for="ta in summary.tool_accuracy" :key="'t'+ta.action_type"
                class="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-xs bg-zinc-50 text-zinc-600">
                <span class="font-mono">{{ ta.action_type }}</span>
                <span class="text-zinc-400">{{ fmtMs(ta.avg_elapsed_ms) }}</span>
              </span>
            </div>
          </div>
        </section>

        <!-- 3. 路径长度 -->
        <section class="rounded-xl border border-zinc-200 bg-white p-5">
          <div class="flex items-center justify-between mb-4">
            <h2 class="text-sm font-semibold text-zinc-800">3️⃣ 路径长度</h2>
            <span class="text-xs text-zinc-400">步骤分布</span>
          </div>
          <div class="grid grid-cols-4 gap-3 mb-4">
            <KPI label="最小" :value="pa.min_steps" unit="步" />
            <KPI label="最大" :value="pa.max_steps" unit="步" />
            <KPI label="均值" :value="pa.mean_steps?.toFixed(1)" unit="步" />
            <KPI label="中位数" :value="pa.median_steps?.toFixed(1)" unit="步" />
          </div>
          <!-- 动作分布 -->
          <div v-if="pa.action_distribution" class="space-y-1.5">
            <div class="text-xs text-zinc-400 mb-1">动作分布</div>
            <div v-for="(ratio, atype) in paddedActionDist" :key="atype" class="flex items-center gap-2">
              <span class="text-xs text-zinc-500 w-12 shrink-0 text-right font-mono">{{ atype }}</span>
              <div class="flex-1 h-3 bg-zinc-100 rounded-full overflow-hidden">
                <div class="h-full rounded-full transition-all duration-700" :class="actionColorClass(atype)" :style="{ width: fmtPct(ratio) }" />
              </div>
              <span class="text-xs text-zinc-400 w-10 shrink-0">{{ fmtPct(ratio) }}</span>
            </div>
          </div>
          <!-- 难度分布 -->
          <div v-if="pa.difficulty_distribution && Object.keys(pa.difficulty_distribution).length" class="mt-4">
            <div class="text-xs text-zinc-400 mb-2">难度分布</div>
            <div class="flex flex-wrap gap-2">
              <span v-for="(count, diff) in pa.difficulty_distribution" :key="diff"
                class="px-2 py-0.5 rounded-md text-xs"
                :class="diffLabelClass(diff)">
                {{ diff }} ×{{ count }}
              </span>
            </div>
          </div>
        </section>

        <!-- 4. 耗时分析 -->
        <section class="rounded-xl border border-zinc-200 bg-white p-5">
          <div class="flex items-center justify-between mb-4">
            <h2 class="text-sm font-semibold text-zinc-800">4️⃣ 耗时分析</h2>
            <span class="text-xs text-zinc-400">毫秒</span>
          </div>
          <div class="grid grid-cols-2 gap-3 mb-4">
            <KPI label="平均总耗时" :value="tp.avg_total_ms" :fmt="fmtMs" />
            <KPI label="每步均耗" :value="tp.avg_per_step_ms" :fmt="fmtMs" />
            <KPI label="P50 耗时" :value="tp.p50_total_ms" :fmt="fmtMs" />
            <KPI label="P95 耗时" :value="tp.p95_total_ms" :fmt="fmtMs" />
          </div>
          <div class="grid grid-cols-2 gap-3 mb-4">
            <KPI label="均 LLM 调用" :value="tp.avg_llm_calls?.toFixed(1)" unit="次/任务" />
            <KPI label="均 Token" :value="tokenDisplay" unit="个/任务" />
          </div>
          <div v-if="tp.slowest_action_type" class="flex items-center gap-2 text-xs">
            <span class="text-zinc-400">最慢动作:</span>
            <span class="px-2 py-0.5 rounded bg-rose-50 text-rose-600 font-mono">{{ tp.slowest_action_type }}</span>
          </div>
        </section>

        <!-- 5. 异常监控 -->
        <section class="rounded-xl border border-zinc-200 bg-white p-5 lg:col-span-2">
          <div class="flex items-center justify-between mb-4">
            <h2 class="text-sm font-semibold text-zinc-800">5️⃣ 异常监控</h2>
            <span class="text-xs text-zinc-400">越低越好</span>
          </div>
          <div class="grid grid-cols-2 md:grid-cols-4 gap-3">
            <AnomalyCard label="空搜索率" :rate="ar.empty_search_rate" color="amber" desc="搜索返回0结果" />
            <AnomalyCard label="空阅读率" :rate="ar.empty_visit_rate" color="amber" desc="阅读未获知识" />
            <AnomalyCard label="评估失败率" :rate="ar.eval_failure_rate" color="rose" desc="门禁不通过" />
            <AnomalyCard label="硬拦截率" :rate="ar.hard_intercept_rate" color="orange" desc="禁止提前answer" />
            <AnomalyCard label="LLM 错误率" :rate="ar.llm_error_rate" color="red" desc="模型调用失败" />
            <AnomalyCard label="Beast Mode" :rate="ar.beast_mode_rate" color="purple" desc="兜底触发" />
            <AnomalyCard label="动作失败率" :rate="ar.action_failure_rate" color="rose" desc="执行异常" />
            <!-- 高频失败类型 -->
            <div v-if="ar.top_failure_types?.length" class="rounded-lg border border-rose-200 bg-rose-50 p-3">
              <div class="text-xs text-rose-500 mb-1">高频失败类型</div>
              <div class="flex flex-wrap gap-1">
                <span v-for="t in ar.top_failure_types" :key="t" class="px-2 py-0.5 rounded text-xs bg-rose-100 text-rose-700 font-mono">{{ t }}</span>
              </div>
            </div>
          </div>
        </section>

      </div>

      <!-- 最近任务列表 -->
      <section class="mt-8">
        <div class="flex items-center justify-between mb-4">
          <h2 class="text-sm font-semibold text-zinc-800">📋 最近任务记录</h2>
          <button @click="loadTasks" class="text-xs text-zinc-400 hover:text-zinc-600 transition">{{ tasks.length }} 条</button>
        </div>
        <div v-if="tasks.length === 0" class="text-xs text-zinc-400 py-4">暂无任务记录</div>
        <div v-else class="overflow-x-auto">
          <table class="w-full text-xs">
            <thead>
              <tr class="border-b border-zinc-100 text-zinc-400">
                <th class="text-left py-2 px-3 font-medium">任务 ID</th>
                <th class="text-left py-2 px-3 font-medium hidden md:table-cell">问题</th>
                <th class="text-center py-2 px-3 font-medium">步骤</th>
                <th class="text-center py-2 px-3 font-medium">知识</th>
                <th class="text-center py-2 px-3 font-medium">引用</th>
                <th class="text-center py-2 px-3 font-medium">状态</th>
                <th class="text-right py-2 px-3 font-medium">耗时</th>
                <th></th>
              </tr>
            </thead>
            <tbody class="divide-y divide-zinc-50">
              <tr v-for="t in tasks" :key="t.task_id" class="hover:bg-zinc-50/60 transition-colors cursor-pointer" @click="selectedTask = t.task_id; loadTaskDetail(t.task_id)">
                <td class="py-2 px-3 font-mono text-zinc-600 truncate max-w-[100px]">{{ t.task_id.slice(0, 12) }}...</td>
                <td class="py-2 px-3 text-zinc-700 truncate max-w-[200px] hidden md:table-cell">{{ t.question }}</td>
                <td class="py-2 px-3 text-center text-zinc-600">{{ t.steps_taken || '?' }}</td>
                <td class="py-2 px-3 text-center text-zinc-600">{{ t.knowledge_count ?? '—' }}</td>
                <td class="py-2 px-3 text-center text-zinc-600">{{ t.ref_count ?? '—' }}</td>
                <td class="py-2 px-3 text-center">
                  <span v-if="t.completed" class="text-emerald-600">✅</span>
                  <span v-else-if="t.completed === false" class="text-rose-500">❌</span>
                  <span v-else class="text-zinc-300">—</span>
                </td>
                <td class="py-2 px-3 text-right text-zinc-500 font-mono">{{ fmtMs(t.total_elapsed_ms) }}</td>
                <td class="py-2 px-3 text-right">
                  <span class="text-zinc-300 hover:text-zinc-500 text-xs">详情 →</span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <!-- 任务详情弹窗 — 三标签：指标 / 答案 / 过程日志 -->
      <Teleport to="body">
        <div v-if="taskDetail" class="fixed inset-0 z-50 flex items-start justify-center pt-16 bg-black/30" @click.self="taskDetail = null">
          <div class="bg-white rounded-2xl shadow-2xl border border-zinc-200 max-w-3xl w-full mx-4 max-h-[80vh] flex flex-col">
            <!-- 标题栏 -->
            <div class="shrink-0 border-b border-zinc-100 p-4 flex items-center justify-between">
              <div class="flex-1 min-w-0">
                <h3 class="text-sm font-semibold text-zinc-800 truncate">{{ taskDetail.question }}</h3>
                <div class="flex gap-3 mt-1 text-xs text-zinc-400">
                  <span>ID: {{ taskDetail.task_id?.slice(0,12) }}</span>
                  <span>{{ taskDetail.steps_taken || '?' }} 步</span>
                  <span v-if="taskDetail.total_elapsed_ms">{{ fmtMs(taskDetail.total_elapsed_ms) }}</span>
                  <span v-if="taskDetail.knowledge_count != null">{{ taskDetail.knowledge_count }} 条知识</span>
                  <span v-if="taskDetail.references?.length">{{ taskDetail.references.length }} 引用</span>
                  <span v-if="taskDetail.beast_mode_triggered" class="text-amber-500">⚡Beast</span>
                </div>
              </div>
              <button @click="taskDetail = null" class="text-zinc-400 hover:text-zinc-600 transition text-xl leading-none ml-4">&times;</button>
            </div>
            <!-- 标签切换 -->
            <div class="shrink-0 flex border-b border-zinc-100 px-4">
              <button v-for="tab in tabs" :key="tab.key"
                @click="activeTab = tab.key"
                :class="[
                  'px-4 py-2 text-xs font-medium transition border-b-2 -mb-[1px]',
                  activeTab === tab.key
                    ? 'text-zinc-800 border-zinc-800'
                    : 'text-zinc-400 border-transparent hover:text-zinc-600'
                ]">
                {{ tab.label }}
              </button>
            </div>
            <!-- 标签内容（可滚动） -->
            <div class="flex-1 overflow-y-auto p-4">
              <!-- Tab 1: 指标 -->
              <div v-if="activeTab === 'metrics'">
                <div v-if="!taskDetail.has_metrics" class="text-center py-10 text-zinc-400">
                  <p class="text-sm">📊 该任务没有指标数据</p>
                  <p class="text-xs mt-2">指标采集器是后来加的，历史任务不会自动补指标。</p>
                </div>
                <div v-else class="space-y-4">
                  <!-- 概览 -->
                  <div class="grid grid-cols-4 gap-2 text-xs">
                    <div class="px-2 py-1.5 bg-zinc-50 rounded"><span class="text-zinc-400">步骤</span> <span class="text-zinc-700 ml-1 font-mono">{{ taskDetail.steps_taken }}/{{ taskDetail.max_steps_allowed }}</span></div>
                    <div class="px-2 py-1.5 bg-zinc-50 rounded"><span class="text-zinc-400">耗时</span> <span class="text-zinc-700 ml-1 font-mono">{{ fmtMs(taskDetail.total_elapsed_ms) }}</span></div>
                    <div class="px-2 py-1.5 bg-zinc-50 rounded"><span class="text-zinc-400">LLM调用</span> <span class="text-zinc-700 ml-1 font-mono">{{ taskDetail.llm_total_calls }} 次</span></div>
                    <div class="px-2 py-1.5 bg-zinc-50 rounded"><span class="text-zinc-400">Token</span> <span class="text-zinc-700 ml-1 font-mono">{{ (taskDetail.llm_total_tokens || 0).toLocaleString() }}</span></div>
                    <div class="px-2 py-1.5 bg-zinc-50 rounded"><span class="text-zinc-400">门禁</span> <span class="text-zinc-700 ml-1">{{ taskDetail.eval_passed ? '✅ 通过' : '❌ 未过' }}</span></div>
                    <div class="px-2 py-1.5 bg-zinc-50 rounded"><span class="text-zinc-400">失败</span> <span class="text-zinc-700 ml-1 font-mono">{{ taskDetail.failed_actions }}</span></div>
                    <div class="px-2 py-1.5 bg-zinc-50 rounded"><span class="text-zinc-400">难度</span> <span :class="diffTagClass(taskDetail.difficulty_label)" class="ml-1">{{ taskDetail.difficulty_label || '—' }}</span></div>
                    <div class="px-2 py-1.5 bg-zinc-50 rounded"><span class="text-zinc-400">异常</span> <span class="text-zinc-700 ml-1 font-mono">{{ anomalyCount }}</span></div>
                  </div>
                  <!-- 动作明细 -->
                  <div v-if="taskDetail.action_records?.length">
                    <div class="text-xs text-zinc-400 font-medium mb-2">动作明细</div>
                    <div class="space-y-1 max-h-52 overflow-y-auto">
                      <div v-for="(r, i) in taskDetail.action_records" :key="i" class="flex items-center gap-2 text-xs py-1 px-2 rounded hover:bg-zinc-50">
                        <span>{{ r.success ? '✅' : '❌' }}</span>
                        <span class="text-zinc-400">step{{ r.step }}</span>
                        <span class="font-mono text-zinc-600 w-16">{{ r.type }}</span>
                        <span class="text-zinc-400 font-mono ml-auto">{{ fmtMs(r.elapsed_ms) }}</span>
                        <span v-if="extraSummary(r)" class="text-zinc-300 ml-2 truncate max-w-[160px]">{{ extraSummary(r) }}</span>
                      </div>
                    </div>
                  </div>
                  <!-- 异常项 -->
                  <div v-if="anomalyList.length" class="text-xs">
                    <span class="text-zinc-400 font-medium">异常:</span>
                    <span v-for="a in anomalyList" :key="a" class="ml-2 px-1.5 py-0.5 bg-rose-50 text-rose-600 rounded">{{ a }}</span>
                  </div>
                </div>
              </div>
              <!-- Tab 2: 答案 -->
              <div v-if="activeTab === 'answer'">
                <div v-if="!taskDetail.answer" class="text-center py-10 text-zinc-400">
                  <p class="text-sm">📝 无答案内容</p>
                </div>
                <div v-else>
                  <div class="prose prose-sm max-w-none text-zinc-700 whitespace-pre-wrap leading-relaxed" v-html="renderedAnswer"></div>
                  <!-- 引用 -->
                  <div v-if="taskDetail.references?.length" class="mt-6 pt-4 border-t border-zinc-100">
                    <div class="text-xs text-zinc-400 font-medium mb-2">📎 引用来源 ({{ taskDetail.references.length }})</div>
                    <div class="space-y-1">
                      <div v-for="(ref, i) in taskDetail.references" :key="i" class="text-xs text-zinc-500 break-all">
                        <a :href="ref" target="_blank" class="text-blue-500 hover:underline">[{{ i+1 }}] {{ ref }}</a>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
              <!-- Tab 3: 过程日志 -->
              <div v-if="activeTab === 'log'">
                <div v-if="!taskDetail.process_log" class="text-center py-10 text-zinc-400">
                  <p class="text-sm">📋 无过程日志</p>
                </div>
                <pre class="text-xs text-zinc-600 whitespace-pre-wrap leading-relaxed font-mono bg-zinc-50 rounded-lg p-4 max-h-[50vh] overflow-y-auto">{{ taskDetail.process_log }}</pre>
              </div>
            </div>
          </div>
        </div>
      </Teleport>

    </template>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { marked } from 'marked'
import { fetchEvalSummary, fetchEvalTask, fetchEvalTasks } from '../api/search.js'

const loading = ref(true)
const summary = ref(null)
const tasks = ref([])
const taskDetail = ref(null)
const selectedTask = ref('')
const activeTab = ref('answer')  // 默认打开答案 tab
const tabs = [
  { key: 'answer', label: '📝 答案' },
  { key: 'metrics', label: '📊 指标' },
  { key: 'log', label: '📋 过程日志' },
]

function simpleMarkdown(text) {
  if (!text) return ''
  try {
    return marked.parse(text)
  } catch {
    // marked 可能未安装，回退到纯文本
    return text.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
      .replace(/\n/g,'<br>')
      .replace(/###? ([^\n]+)/g,'<strong>$1</strong>')
  }
}

// 加载聚合摘要
async function loadSummary() {
  try {
    const res = await fetchEvalSummary()
    summary.value = res.data
  } catch (e) {
    console.error('加载评估摘要失败:', e)
  } finally {
    loading.value = false
  }
}

// 加载任务列表
async function loadTasks() {
  try {
    tasks.value = await fetchEvalTasks()
  } catch { /* ignore */ }
}

// 加载单任务详情
async function loadTaskDetail(taskId) {
  try {
    const res = await fetchEvalTask(taskId)
    taskDetail.value = res.data
  } catch { /* ignore */ }
}

// 计算属性
const tc = computed(() => summary.value?.task_completion || {})
const pa = computed(() => summary.value?.path_analysis || {})
const tp = computed(() => summary.value?.timing_profile || {})
const ar = computed(() => summary.value?.anomaly_report || {})

const beastCount = computed(() => Math.round((tc.value.beast_mode_rate || 0) * (tc.value.total_tasks || 0)))
const tokenDisplay = computed(() => Math.round(tp.value.avg_llm_tokens || 0).toLocaleString())

// 异常列表
const anomalyList = computed(() => {
  if (!taskDetail.value) return []
  const d = taskDetail.value
  const list = []
  if (d.empty_searches) list.push(`空搜索×${d.empty_searches}`)
  if (d.empty_visits) list.push(`空阅读×${d.empty_visits}`)
  if (d.evaluation_failures) list.push(`评估失败×${d.evaluation_failures}`)
  if (d.hard_intercepts) list.push(`硬拦截×${d.hard_intercepts}`)
  if (d.llm_errors) list.push(`LLM错误×${d.llm_errors}`)
  return list
})
const anomalyCount = computed(() => {
  const d = taskDetail.value
  if (!d) return 0
  return (d.empty_searches||0) + (d.empty_visits||0) + (d.evaluation_failures||0) + (d.hard_intercepts||0) + (d.llm_errors||0)
})
const renderedAnswer = computed(() => simpleMarkdown(taskDetail.value?.answer || ''))

// 动作分布按指定顺序排列（补零）
const paddedActionDist = computed(() => {
  const dist = { ...(pa.value?.action_distribution || {}) }
  const order = ['search', 'visit', 'reflect', 'rewrite', 'answer']
  const res = {}
  for (const k of order) {
    res[k] = dist[k] || 0
  }
  return res
})

// 格式化
function fmtPct(v) { return v != null ? `${(v * 100).toFixed(0)}%` : '0%' }
function fmtMs(v) {
  if (!v) return '0ms'
  if (v < 1000) return `${v.toFixed(0)}ms`
  if (v < 60000) return `${(v/1000).toFixed(1)}s`
  const m = Math.floor(v / 60000)
  const s = Math.round((v % 60000) / 1000)
  return `${m}m${s}s`
}
function rateColorClass(r) {
  if (r >= 0.8) return 'bg-emerald-500'
  if (r >= 0.6) return 'bg-amber-500'
  return 'bg-rose-500'
}
function rateTextClass(r) {
  if (r >= 0.8) return 'text-emerald-600'
  if (r >= 0.6) return 'text-amber-600'
  return 'text-rose-600'
}
function actionColorClass(type) {
  const m = { search: 'bg-blue-400', visit: 'bg-emerald-400', reflect: 'bg-purple-400', rewrite: 'bg-orange-400', answer: 'bg-rose-400', beast_mode: 'bg-red-500' }
  return m[type] || 'bg-zinc-400'
}
function diffLabelClass(d) {
  const m = { '简单': 'bg-emerald-50 text-emerald-700', '中等': 'bg-amber-50 text-amber-700', '困难': 'bg-rose-50 text-rose-700', '未知': 'bg-zinc-50 text-zinc-500' }
  return m[d] || 'bg-zinc-50 text-zinc-500'
}
function diffTagClass(d) {
  const m = { '简单': 'text-emerald-600', '中等': 'text-amber-600', '困难': 'text-rose-600' }
  return m[d] || 'text-zinc-400'
}
function extraSummary(r) {
  if (!r.extra) return ''
  const e = r.extra
  if (r.type === 'search') return `结果:${e.results_found ?? '?'}`
  if (r.type === 'visit') return `知识:${e.knowledge_extracted ?? '?'}`
  if (r.type === 'answer') return `${e.eval_passed ? '✅' : '❌'} ${e.char_count ?? 0}字`
  return ''
}

onMounted(() => {
  loadSummary()
  loadTasks()
})
</script>

<script>
import { h } from 'vue'

const StatCard = {
  props: ['label', 'value', 'trend', 'color', 'invert'],
  setup(props) {
    const cols = { slate: 'bg-slate-50 border-slate-200', emerald: 'bg-emerald-50 border-emerald-200', blue: 'bg-blue-50 border-blue-200', amber: 'bg-amber-50 border-amber-200', rose: 'bg-rose-50 border-rose-200' }
    const texts = { slate: 'text-slate-700', emerald: 'text-emerald-700', blue: 'text-blue-700', amber: 'text-amber-700', rose: 'text-rose-700' }
    const subs = { slate: 'text-slate-500', emerald: 'text-emerald-600', blue: 'text-blue-600', amber: 'text-amber-600', rose: 'text-rose-600' }
    const icon = props.invert
      ? (props.trend === 'up' ? '↑' : '↓')
      : (props.trend === 'up' ? '↑' : props.trend === 'down' ? '↓' : '')
    const iconColor = props.invert
      ? (props.trend === 'up' ? 'text-rose-500' : 'text-emerald-500')
      : (props.trend === 'up' ? 'text-emerald-500' : 'text-rose-500')
    return () => h('div', { class: `rounded-xl border px-4 py-3 ${cols[props.color] || cols.slate}` }, [
      h('div', { class: `text-xs ${subs[props.color] || subs.slate} mb-1` }, props.label),
      h('div', { class: 'flex items-baseline gap-1' }, [
        h('span', { class: `text-xl font-bold ${texts[props.color] || texts.slate}` }, String(props.value)),
        icon ? h('span', { class: `text-xs ${iconColor}` }, icon) : null,
      ]),
    ])
  },
}

const KPI = {
  props: ['label', 'value', 'unit', 'fmt'],
  setup(props) {
    const display = props.fmt ? props.fmt(props.value) : (props.value ?? '—')
    return () => h('div', { class: 'px-3 py-2 bg-zinc-50 rounded-lg' }, [
      h('div', { class: 'text-xs text-zinc-400' }, props.label),
      h('div', { class: 'text-sm font-semibold text-zinc-700' }, [
        h('span', {}, String(display)),
        props.unit ? h('span', { class: 'text-xs text-zinc-400 ml-0.5' }, props.unit) : null,
      ]),
    ])
  },
}

const MiniRow = {
  props: ['label', 'val', 'total', 'color'],
  setup(props) {
    const pct = props.total ? Math.round((props.val / props.total) * 100) : 0
    const cls = { emerald: 'bg-emerald-100 text-emerald-700', amber: 'bg-amber-100 text-amber-700', blue: 'bg-blue-100 text-blue-700' }
    return () => h('div', { class: `px-2 py-1 rounded text-xs text-center ${cls[props.color] || 'bg-zinc-100 text-zinc-600'}` }, [
      h('div', { class: 'opacity-70' }, props.label),
      h('div', { class: 'font-semibold' }, `${props.val} (${pct}%)`),
    ])
  },
}

const AnomalyCard = {
  props: ['label', 'rate', 'color', 'desc'],
  setup(props) {
    const r = props.rate ?? 0
    const thresholds = { amber: 0.2, orange: 0.2, rose: 0.1, red: 0.05, purple: 0.3 }
    const threshold = thresholds[props.color] || 0.1
    const isHigh = r > threshold
    const bgMap = { amber: 'border-amber-300 bg-amber-50', orange: 'border-orange-300 bg-orange-50', rose: 'border-rose-300 bg-rose-50', red: 'border-red-300 bg-red-50', purple: 'border-purple-300 bg-purple-50' }
    const bg = isHigh ? (bgMap[props.color] || 'border-rose-300 bg-rose-50') : 'border-zinc-200 bg-white'
    return () => h('div', { class: `rounded-lg border px-3 py-2.5 ${bg}` }, [
      h('div', { class: 'text-xs text-zinc-400' }, props.label),
      h('div', { class: `text-lg font-bold ${isHigh ? 'text-rose-600' : 'text-zinc-600'}` }, `${(r * 100).toFixed(1)}%`),
      h('div', { class: 'text-xs text-zinc-400 mt-0.5' }, props.desc),
    ])
  },
}

export default {
  components: { StatCard, KPI, MiniRow, AnomalyCard },
}
</script>
