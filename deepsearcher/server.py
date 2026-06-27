#!/usr/bin/env python3
"""
Deep Research Web API — FastAPI + SSE 实时推流后端
"""

import asyncio
import json
import logging
import os
import sys
import time
import uuid
from datetime import datetime
from typing import Optional

# ── 自动挂载 venv ──────────────────────────────────────────────
_venv = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'venv')
if os.path.isdir(_venv):
    _sp = os.path.join(_venv, 'lib', f'python{sys.version_info.major}.{sys.version_info.minor}', 'site-packages')
    if os.path.isdir(_sp) and _sp not in sys.path:
        sys.path.insert(0, _sp)

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .agent import deep_research as deep_search
from .config import MAX_TURNS, TOKEN_BUDGET
from .evaluator.storage import MetricsStorage, compute_summary
from .evaluator.reporter import MetricsReporter

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("server")

# ── 任务管理 ────────────────────────────────────────────────────
class SearchTask:
    def __init__(self, question: str, max_turns: int, token_budget: int):
        self.task_id = uuid.uuid4().hex[:12]
        self.question = question
        self.max_turns = max_turns
        self.token_budget = token_budget
        self.queue: asyncio.Queue = asyncio.Queue()
        self.result: Optional[dict] = None
        self.done = False
        self.error: Optional[str] = None
        self.created_at = time.time()
        self._process_diary: list[dict] = []  # 每个步骤的详细记录

    async def run(self):
        """后台运行研究"""
        try:
            async def on_event(state: dict):
                # 推送精简状态到 SSE
                payload = {
                    "step": state["step_count"],
                    "diary": state["diary_context"][-1] if state["diary_context"] else "",
                    "knowledge_count": len(state["all_knowledge"]),
                    "url_count": len(state["all_urls"]),
                    "visited_count": len(set(state.get("visited_urls", []))),
                    "final_answer": state.get("final_answer", ""),
                    "references": state.get("references", []),
                    "done": bool(state.get("final_answer")),
                }
                await self.queue.put(("event", payload))

            result = await deep_search(
                question=self.question,
                max_turns=self.max_turns,
                token_budget=self.token_budget,
                event_callback=on_event,
                task_id=self.task_id,
            )
            self.result = result
            self.done = True
            await self.queue.put(("event", {
                "step": result["steps"],
                "diary": "研究完成 ✅",
                "knowledge_count": result["knowledge_count"],
                "url_count": 0,
                "visited_count": len(result["references"]),
                "final_answer": result["answer"],
                "references": result["references"],
                "done": True,
            }))
            # ── 持久化 ──
            await _persist_result(self)
        except Exception as e:
            self.error = str(e)
            self.done = True
            await self.queue.put(("error", str(e)))
            # ── 即使报错也持久化 ──
            await _persist_result(self)
        finally:
            await self.queue.put(None)  # 结束信号

    async def event_stream(self):
        """SSE 事件流"""
        try:
            while True:
                item = await self.queue.get()
                if item is None:
                    break
                kind, data = item
                if kind == "event":
                    yield f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
                elif kind == "error":
                    yield f"event: error\ndata: {json.dumps({'error': data}, ensure_ascii=False)}\n\n"
        except asyncio.CancelledError:
            pass


# ── 持久化 ─────────────────────────────────────────────────────
RESULTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")

def _ensure_results_dir():
    os.makedirs(RESULTS_DIR, exist_ok=True)

def _rebuild_index():
    """从已有的 .json 任务文件重建 index.json"""
    index_path = os.path.join(RESULTS_DIR, "index.json")
    index = []
    if os.path.isdir(RESULTS_DIR):
        for fname in os.listdir(RESULTS_DIR):
            if not fname.endswith(".json") or fname == "index.json":
                continue
            fp = os.path.join(RESULTS_DIR, fname)
            try:
                with open(fp, "r", encoding="utf-8") as f:
                    d = json.load(f)
            except Exception:
                continue
            result = d.get("result") or {}
            refs = result.get("references") or {}
            index.append({
                "task_id": d.get("task_id", fname[:-5]),
                "question": d.get("question", ""),
                "steps": result.get("steps", "?"),
                "knowledge_count": result.get("knowledge_count", 0),
                "ref_count": len(refs) if isinstance(refs, list) else 0,
                "timestamp": d.get("created_at", 0),
            })
    index.sort(key=lambda x: x["timestamp"], reverse=True)
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)

async def _persist_result(task: SearchTask):
    """将任务结果写入文件系统"""
    _ensure_results_dir()
    created_str = datetime.fromtimestamp(task.created_at).strftime("%Y-%m-%d %H:%M:%S")

    # ── 0. 原始结果 JSON（用于 restart 后恢复）──
    raw_path = os.path.join(RESULTS_DIR, f"{task.task_id}.json")
    if not os.path.exists(raw_path):
        with open(raw_path, "w", encoding="utf-8") as f:
            json.dump({
                "question": task.question,
                "result": task.result,
                "done": task.done,
                "created_at": task.created_at,
            }, f, ensure_ascii=False)

    # ── 1. 结果 .md 文件 ──
    result_path = os.path.join(RESULTS_DIR, f"{task.task_id}.md")
    result = task.result or {}
    answer = result.get("answer", "") or ""
    references = result.get("references", []) or []
    diary = result.get("diary", []) or []

    # 参考资料：编号+分段，与正文区分
    refs_lines = []
    for i, ref in enumerate(references, 1):
        refs_lines.append(f"  [{i}] {ref}")
    refs_text = "\n".join(refs_lines)
    # 结构化呈现：按步骤分组
    proc_lines = []
    for entry in diary:
        stripped = entry.strip()
        if stripped.startswith("═══ 步骤"):
            proc_lines.append(f"\n**{stripped}**")
        elif stripped.startswith("  ├"):
            # 进度快照用缩进 + 暗色标记
            proc_lines.append(f"\n└─ {stripped.strip(' ├')}")
        elif stripped.startswith("[step"):
            proc_lines.append(f"\n    📡 {stripped}")
        elif stripped.startswith("[plan"):
            proc_lines.append(f"    📋 {stripped}")
        elif stripped.startswith("[evaluate_question"):
            proc_lines.append(f"    🔍 {stripped}")
        elif stripped.startswith("[search"):
            proc_lines.append(f"    🔎 {stripped}")
        elif stripped.startswith("[visit"):
            proc_lines.append(f"    📖 {stripped}")
        elif stripped.startswith("[⛔"):
            proc_lines.append(f"    🚫 {stripped}")
        elif stripped.startswith("[answer"):
            proc_lines.append(f"    📝 {stripped}")
        elif stripped.startswith("[evaluate"):
            proc_lines.append(f"    ❌ {stripped}")
        elif stripped.startswith("[beast_mode"):
            proc_lines.append(f"    ⚠️ {stripped}")
        elif stripped.startswith("[error"):
            proc_lines.append(f"    🔴 {stripped}")
        elif stripped.startswith("[reflect"):
            proc_lines.append(f"    🔄 {stripped}")
        elif stripped:
            proc_lines.append(f"    {stripped}")
    process_text = "\n".join(proc_lines)

    md_content = f"""# 深度研究报告

**问题**: {task.question}

**时间**: {created_str}

**元信息**:
- 步骤: {result.get('steps', '?')}
- 知识提取: {result.get('knowledge_count', 0)} 条
- 引用: {len(references)} 个
- Beast Mode: {'是' if result.get('beast_mode_used') else '否'}

---

## 📖 最终答案

{answer}

---

### 📎 引用来源
{refs_text or '  无引用'}

---

## 📋 研究过程

{process_text}

---
"""
    with open(result_path, "w", encoding="utf-8") as f:
        f.write(md_content)

    # ── 2. 过程日志 .md 文件 ──
    process_path = os.path.join(RESULTS_DIR, f"{task.task_id}_过程日志.md")
    proc_content = f"""# 深度研究过程日志

**问题**: {task.question}
**时间**: {created_str}

## 每步记录

{process_text}

## 参考资料
{refs_text or '  无引用'}

## 原始状态摘要

- 总步骤: {result.get('steps', '?')}
- 知识提取数: {result.get('knowledge_count', 0)} 条
- 引用数: {len(references)}
- Beast Mode 触发: {'是' if result.get('beast_mode_used') else '否'}
"""
    with open(process_path, "w", encoding="utf-8") as f:
        f.write(proc_content)

    # ── 3. 更新索引 ──
    index_path = os.path.join(RESULTS_DIR, "index.json")
    if os.path.exists(index_path):
        with open(index_path, "r", encoding="utf-8") as f:
            index = json.load(f)
    else:
        index = []

    # 去重：同 task_id 不重复记录
    index = [e for e in index if e.get("task_id") != task.task_id]
    index.append({
        "task_id": task.task_id,
        "question": task.question,
        "created_at": task.created_at,
        "created_str": created_str,
        "steps": result.get("steps", 0),
        "knowledge_count": result.get("knowledge_count", 0),
        "ref_count": len(references),
        "beast_mode_used": result.get("beast_mode_used", False),
        "error": task.error,
    })
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)


# ── 全局任务池 ──────────────────────────────────────────────────
tasks: dict[str, SearchTask] = {}

# ── Cleanup ─────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时：为旧版 .md 结果补充 .json（若无）
    def _migrate_legacy_md_to_json(fname: str):
        """将没有 .json 的旧 .md 文件迁移为 .json"""
        task_id = fname[:-3]
        json_path = os.path.join(RESULTS_DIR, f"{task_id}.json")
        if os.path.exists(json_path):
            return

        md_path = os.path.join(RESULTS_DIR, fname)
        with open(md_path, "r", encoding="utf-8") as f:
            content = f.read()

        import re

        # 提取 question（第一行 **问题**: 后面的内容）
        mq = re.search(r'\*\*问题\*\*:\s*(.*)', content)
        question = mq.group(1).strip() if mq else ""

        # 提取 answer（兼容新旧格式）
        def _extract_answer(text: str) -> str:
            if '## 📖 最终答案' in text:
                m = re.search('## 📖 最终答案\n(.*?)(?=\n---\n\n### 📎 引用来源|\n---\n\n## 📋 研究过程)', text, re.DOTALL)
                if m:
                    return m.group(1).strip()
                m = re.search('## 📖 最终答案\n(.*?)(?=\n## |$)', text, re.DOTALL)
                return m.group(1).strip() if m else text[:500]
            # 旧格式：第一个 --- 到倒数第二个 ---
            positions = [m.start() for m in re.finditer(r'\n---\n', text)]
            if len(positions) >= 2:
                start = positions[0] + 5
                end = positions[-2]
                return text[start:end].strip()
            if len(positions) >= 1:
                start = positions[0] + 5
                return text[start:].strip()
            return text[:500]
        answer = _extract_answer(content)

        # 提取 steps
        m_steps = re.search(r'- 步骤:\s*([\d?]+)', content)
        steps_val = int(m_steps.group(1)) if m_steps and m_steps.group(1).isdigit() else "?"

        with open(json_path, "w", encoding="utf-8") as f:
            json.dump({
                "question": question,
                "result": {
                    "answer": answer,
                    "references": [],
                    "diary": [],
                    "steps": steps_val,
                    "knowledge_count": 0,
                },
                "done": True,
                "created_at": time.time(),
            }, f, ensure_ascii=False)

    _ensure_results_dir()
    if os.path.exists(RESULTS_DIR):
        for fname in os.listdir(RESULTS_DIR):
            if fname.endswith(".md") and not fname.endswith("_过程日志.md"):
                _migrate_legacy_md_to_json(fname)
    # 重建 index.json（从已有 .json 文件）
    _rebuild_index()
    yield
    # 清理过期任务（> 1 小时）
    now = time.time()
    for tid, task in list(tasks.items()):
        if now - task.created_at > 3600:
            del tasks[tid]


# ── FastAPI App ────────────────────────────────────────────────
app = FastAPI(title="Deep Research API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── API 路由 ───────────────────────────────────────────────────
class SearchRequest(BaseModel):
    question: str
    max_turns: int = MAX_TURNS
    token_budget: int = TOKEN_BUDGET


@app.post("/api/search")
async def start_search(req: SearchRequest):
    """启动研究，返回 task_id"""
    if not req.question.strip():
        raise HTTPException(400, "问题不能为空")

    task = SearchTask(
        question=req.question.strip(),
        max_turns=min(req.max_turns, 10),
        token_budget=min(req.token_budget, 200000),
    )
    tasks[task.task_id] = task
    asyncio.create_task(task.run())

    return {
        "task_id": task.task_id,
        "question": task.question,
        "max_turns": task.max_turns,
    }


@app.get("/api/stream/{task_id}")
async def stream_events(task_id: str):
    """SSE 推流"""
    task = tasks.get(task_id)
    if not task:
        raise HTTPException(404, "任务不存在")

    return StreamingResponse(
        task.event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/result/{task_id}")
async def get_result(task_id: str):
    """获取研究结果（先查内存，再落盘）"""
    task = tasks.get(task_id)
    if task:
        if not task.done:
            raise HTTPException(400, "任务尚未完成")
        return {
            "done": True,
            "result": task.result,
            "error": task.error,
        }

    # 不在内存中 → 从磁盘恢复
    _ensure_results_dir()
    raw_path = os.path.join(RESULTS_DIR, f"{task_id}.json")
    if os.path.exists(raw_path):
        with open(raw_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {
            "done": True,
            "result": data.get("result", {}),
            "error": None,
        }
    # 无 .json 文件（旧版数据），尝试从 .md 提取答案
    md_path = os.path.join(RESULTS_DIR, f"{task_id}.md")
    if os.path.exists(md_path):
        with open(md_path, "r", encoding="utf-8") as f:
            content = f.read()
        import re
        def _extract_answer(text: str) -> str:
            if '## 📖 最终答案' in text:
                m = re.search('## 📖 最终答案\n(.*?)(?=\n---\n\n### 📎 引用来源|\n---\n\n## 📋 研究过程)', text, re.DOTALL)
                if m:
                    return m.group(1).strip()
                m = re.search('## 📖 最终答案\n(.*?)(?=\n## |$)', text, re.DOTALL)
                return m.group(1).strip() if m else text[:500]
            positions = [m.start() for m in re.finditer(r'\n---\n', text)]
            if len(positions) >= 2:
                start = positions[0] + 5
                end = positions[-2]
                return text[start:end].strip()
            if len(positions) >= 1:
                start = positions[0] + 5
                return text[start:].strip()
            return text[:500]
        answer = _extract_answer(content)
        return {
            "done": True,
            "result": {"answer": answer, "references": [], "diary": [], "steps": "?", "knowledge_count": 0},
            "error": None,
        }
    raise HTTPException(404, "任务不存在")


@app.get("/api/tasks")
async def list_tasks():
    """列出所有运行中的任务"""
    return {
        tid: {
            "question": t.question[:40],
            "done": t.done,
            "created": t.created_at,
        }
        for tid, t in tasks.items()
    }


# ── 评估 API ───────────────────────────────────────────────────

@app.get("/api/eval/summary")
async def get_eval_summary():
    """获取 Agent 效果评估全量聚合摘要"""
    try:
        storage = MetricsStorage()
        summary = compute_summary(storage)
        reporter = MetricsReporter(storage)
        return {
            "text_report": reporter.format_text(summary),
            "data": {
                "total_tasks": summary.total_tasks,
                "generated_at": summary.generated_at,
                "task_completion": {
                    "total": summary.task_completion.total_tasks,
                    "completed": summary.task_completion.completed,
                    "completion_rate": summary.task_completion.completion_rate,
                    "beast_mode_rate": summary.task_completion.beast_mode_rate,
                    "eval_pass_rate": summary.task_completion.eval_pass_rate,
                },
                "tool_accuracy": [
                    {
                        "action_type": ta.action_type,
                        "total": ta.total,
                        "successful": ta.successful,
                        "success_rate": ta.success_rate,
                        "avg_elapsed_ms": ta.avg_elapsed_ms,
                    }
                    for ta in summary.tool_accuracy
                ],
                "path_analysis": {
                    "min_steps": summary.path_analysis.min_steps,
                    "max_steps": summary.path_analysis.max_steps,
                    "mean_steps": summary.path_analysis.mean_steps,
                    "median_steps": summary.path_analysis.median_steps,
                    "action_distribution": summary.path_analysis.action_distribution,
                    "difficulty_distribution": summary.path_analysis.difficulty_distribution,
                },
                "timing_profile": {
                    "avg_total_ms": summary.timing_profile.avg_total_ms,
                    "avg_per_step_ms": summary.timing_profile.avg_per_step_ms,
                    "p50_total_ms": summary.timing_profile.p50_total_ms,
                    "p95_total_ms": summary.timing_profile.p95_total_ms,
                    "avg_llm_calls": summary.timing_profile.avg_llm_calls,
                    "avg_llm_tokens": summary.timing_profile.avg_llm_tokens,
                    "slowest_action_type": summary.timing_profile.slowest_action_type,
                    "action_avg_timing": summary.timing_profile.action_avg_timing,
                },
                "anomaly_report": {
                    "empty_search_rate": summary.anomaly_report.empty_search_rate,
                    "empty_visit_rate": summary.anomaly_report.empty_visit_rate,
                    "eval_failure_rate": summary.anomaly_report.eval_failure_rate,
                    "hard_intercept_rate": summary.anomaly_report.hard_intercept_rate,
                    "llm_error_rate": summary.anomaly_report.llm_error_rate,
                    "beast_mode_rate": summary.anomaly_report.beast_mode_rate,
                    "action_failure_rate": summary.anomaly_report.action_failure_rate,
                    "top_failure_types": summary.anomaly_report.top_failure_types,
                },
            },
        }
    except Exception as e:
        raise HTTPException(500, f"评估摘要生成失败: {e}")


@app.get("/api/eval/text")
async def get_eval_text_report():
    """获取纯文本格式评估报告"""
    try:
        storage = MetricsStorage()
        summary = compute_summary(storage)
        reporter = MetricsReporter(storage)
        from fastapi.responses import PlainTextResponse
        return PlainTextResponse(reporter.format_text(summary))
    except Exception as e:
        raise HTTPException(500, f"文本报告生成失败: {e}")


@app.get("/api/eval/tasks")
async def list_eval_tasks():
    """列出所有任务（合并评估指标 + 历史结果）"""
    try:
        storage = MetricsStorage()
        metrics_index = storage.get_metrics_index()
        metrics_ids = {e["task_id"] for e in metrics_index}

        # 合并 results/index.json 中的历史任务
        _ensure_results_dir()
        results_index_path = os.path.join(RESULTS_DIR, "index.json")
        if os.path.exists(results_index_path):
            with open(results_index_path, "r", encoding="utf-8") as f:
                results_index = json.load(f)
        else:
            results_index = []

        merged = list(metrics_index)  # 指标任务优先
        for entry in results_index:
            tid = entry.get("task_id", "")
            if tid and tid not in metrics_ids:
                merged.append({
                    "task_id": tid,
                    "question": entry.get("question", "")[:60],
                    "created_at": entry.get("timestamp", entry.get("created_at", 0)),
                    "steps_taken": entry.get("steps", 0) if isinstance(entry.get("steps"), int) else 0,
                    "completed": True,
                    "eval_passed": False,
                    "total_elapsed_ms": 0,
                    "difficulty_label": "",
                    "beast_mode_triggered": entry.get("beast_mode_used", False),
                    "knowledge_count": entry.get("knowledge_count", 0),
                    "ref_count": entry.get("ref_count", 0),
                })

        merged.sort(key=lambda x: x.get("created_at", 0), reverse=True)
        return merged
    except Exception as e:
        raise HTTPException(500, f"任务列表获取失败: {e}")


@app.get("/api/eval/task/{task_id}")
async def get_eval_task(task_id: str):
    """获取单个任务的详细指标 + 答案 + 过程日志"""
    try:
        storage = MetricsStorage()
        metrics = storage.load_task_metrics(task_id)

        # 从 results/ 读取答案和过程日志
        _ensure_results_dir()
        result_path = os.path.join(RESULTS_DIR, f"{task_id}.json")
        rdata = None
        question = ""
        answer = ""
        references = []
        diary = []
        knowledge_count = 0
        beast_mode_used = False
        if os.path.exists(result_path):
            try:
                with open(result_path, "r", encoding="utf-8") as f:
                    rdata = json.load(f)
            except Exception:
                rdata = None
        if rdata:
            result = rdata.get("result") or {}
            question = rdata.get("question", "") or ""
            answer = result.get("answer", "") or ""
            references = result.get("references", []) or []
            diary = result.get("diary", []) or []
            knowledge_count = result.get("knowledge_count", 0)
            beast_mode_used = result.get("beast_mode_used", False)

        # 过程日志
        process_text = ""
        process_path = os.path.join(RESULTS_DIR, f"{task_id}_过程日志.md")
        if os.path.exists(process_path):
            with open(process_path, "r", encoding="utf-8") as f:
                process_text = f.read()
        elif diary:
            # 从结果文件构建
            proc_lines = []
            for entry in diary:
                stripped = entry.strip()
                if stripped.startswith("═══ 步骤"):
                    proc_lines.append(f"\n**{stripped}**")
                elif stripped:
                    proc_lines.append(f"    {stripped}")
            process_text = "\n".join(proc_lines)

        # 尝试从 metrics 或 index.json 获取问题标题
        if not question and metrics:
            question = metrics.question or ""
        if not question:
            # 从 results/index.json 找
            results_idx_path = os.path.join(RESULTS_DIR, "index.json")
            if os.path.exists(results_idx_path):
                try:
                    with open(results_idx_path, "r", encoding="utf-8") as f:
                        results_idx = json.load(f)
                    for entry in results_idx:
                        if entry.get("task_id") == task_id:
                            question = entry.get("question", "") or ""
                            break
                except Exception:
                    pass

        if not metrics:
            # 历史任务无指标数据，返回基本信息
            return {
                "data": {
                    "task_id": task_id,
                    "question": question,
                    "completed": True,
                    "steps_taken": len(diary) if diary else 0,
                    "max_steps_allowed": 0,
                    "total_elapsed_ms": 0,
                    "answer": answer,
                    "references": references,
                    "knowledge_count": knowledge_count,
                    "beast_mode_triggered": beast_mode_used,
                    "process_log": process_text,
                    "action_records": [],
                    "has_metrics": False,
                },
            }

        reporter = MetricsReporter(storage)
        return {
            "text_report": reporter.format_task_text(metrics),
            "data": {
                "task_id": metrics.task_id,
                "question": metrics.question,
                "completed": metrics.completed,
                "beast_mode_triggered": metrics.beast_mode_triggered,
                "eval_passed": metrics.eval_passed,
                "eval_attempts": metrics.eval_attempts,
                "total_actions": metrics.total_actions,
                "successful_actions": metrics.successful_actions,
                "steps_taken": metrics.steps_taken,
                "max_steps_allowed": metrics.max_steps_allowed,
                "actions_by_type": metrics.actions_by_type,
                "total_elapsed_ms": metrics.total_elapsed_ms,
                "per_step_avg_ms": metrics.per_step_avg_ms,
                "llm_total_calls": metrics.llm_total_calls,
                "llm_total_tokens": metrics.llm_total_tokens,
                "action_timing": metrics.action_timing,
                "failed_actions": metrics.failed_actions,
                "empty_searches": metrics.empty_searches,
                "empty_visits": metrics.empty_visits,
                "evaluation_failures": metrics.evaluation_failures,
                "hard_intercepts": metrics.hard_intercepts,
                "llm_errors": metrics.llm_errors,
                "created_at": metrics.created_at,
                "difficulty_label": metrics.difficulty_label,
                "answer": answer,
                "references": references,
                "knowledge_count": knowledge_count,
                "process_log": process_text,
                "has_metrics": True,
                "action_records": [
                    {
                        "type": r.action_type,
                        "step": r.step,
                        "success": r.success,
                        "elapsed_ms": r.elapsed_ms,
                        "llm_calls": r.llm_calls,
                        "extra": r.extra,
                    }
                    for r in metrics.action_records
                ],
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"任务指标获取失败: {e}")


@app.get("/api/eval/export")
async def export_eval_json():
    """导出完整 JSON 评估报告"""
    try:
        storage = MetricsStorage()
        reporter = MetricsReporter(storage)
        return {"json": reporter.export_json()}
    except Exception as e:
        raise HTTPException(500, f"导出失败: {e}")


@app.get("/api/eval/text/{task_id}")
async def get_eval_task_text(task_id: str):
    """获取单个任务的纯文本指标报告"""
    try:
        storage = MetricsStorage()
        metrics = storage.load_task_metrics(task_id)
        if not metrics:
            raise HTTPException(404, f"任务 {task_id} 的指标不存在")
        reporter = MetricsReporter(storage)
        from fastapi.responses import PlainTextResponse
        return PlainTextResponse(reporter.format_task_text(metrics))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"文本报告生成失败: {e}")


# ── 历史 API ───────────────────────────────────────────────────
@app.get("/api/history")
async def list_history():
    """列出所有历史任务结果"""
    _ensure_results_dir()
    index_path = os.path.join(RESULTS_DIR, "index.json")
    if os.path.exists(index_path):
        with open(index_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


@app.get("/api/history/{task_id}")
async def get_history_result(task_id: str):
    """获取历史任务的原始结果（含 answer 和参考文献）"""
    _ensure_results_dir()
    result_path = os.path.join(RESULTS_DIR, f"{task_id}.md")
    if not os.path.exists(result_path):
        raise HTTPException(404, "历史结果不存在")
    with open(result_path, "r", encoding="utf-8") as f:
        content = f.read()
    return {"task_id": task_id, "content": content}


@app.get("/api/process/{task_id}")
async def get_process_log(task_id: str):
    """获取历史任务的过程日志"""
    _ensure_results_dir()
    process_path = os.path.join(RESULTS_DIR, f"{task_id}_过程日志.md")
    if os.path.exists(process_path):
        with open(process_path, "r", encoding="utf-8") as f:
            content = f.read()
    else:
        # 回退到结果文件
        result_path = os.path.join(RESULTS_DIR, f"{task_id}.md")
        if os.path.exists(result_path):
            with open(result_path, "r", encoding="utf-8") as f:
                content = f.read()
        else:
            raise HTTPException(404, "过程日志不存在")
    return {"task_id": task_id, "content": content}


# ── 静态文件 ────────────────────────────────────────────────────
STATIC_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "vue", "dist")
if os.path.isdir(STATIC_DIR):
    app.mount("/assets", StaticFiles(directory=os.path.join(STATIC_DIR, "assets")), name="assets")

    @app.get("/")
    async def index():
        """提供前端页面"""
        index_path = os.path.join(STATIC_DIR, "index.html")
        if os.path.exists(index_path):
            return FileResponse(index_path, media_type="text/html")
        return {"message": "Deep Research API is running. Build frontend with `cd vue && npm run build`"}

    @app.get("/{full_path:path}")
    async def spa_fallback(full_path: str):
        """SPA 回退：所有非 API 路由都返回 index.html（客户端路由）"""
        if full_path.startswith("api/"):
            raise HTTPException(404, "API 端点不存在")
        index_path = os.path.join(STATIC_DIR, "index.html")
        if os.path.exists(index_path):
            return FileResponse(index_path, media_type="text/html")
        return {"message": "Not found"}
else:
    @app.get("/")
    async def index():
        return {"message": "Deep Research static build not found. Run `cd vue && npm run build` first"}


# ── 启动 ────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080, log_level="info")
