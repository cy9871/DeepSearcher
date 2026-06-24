import { createRouter, createWebHistory } from 'vue-router'
import InputView from '../views/InputView.vue'
import RunningView from '../views/RunningView.vue'
import ResultView from '../views/ResultView.vue'
import HistoryView from '../views/HistoryView.vue'
import ProcessView from '../views/ProcessView.vue'
import EvalView from '../views/EvalView.vue'

const routes = [
  { path: '/', name: 'input', component: InputView },
  { path: '/run/:taskId', name: 'running', component: RunningView },
  { path: '/result/:taskId', name: 'result', component: ResultView },
  { path: '/history', name: 'history', component: HistoryView },
  { path: '/process/:taskId', name: 'process', component: ProcessView },
  { path: '/eval', name: 'eval', component: EvalView },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

export default router
