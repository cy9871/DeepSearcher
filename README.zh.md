# DeepSearcher

一个多轮循环研究 Agent，专门对付复杂问题。

大模型面对复杂问题经常给一个笼统的答案。追问细节它就编造，只搜一次覆盖面不够。DeepSearcher 通过「搜索→阅读→反思→改写→再搜索」的循环不断逼近深度答案。

[English](./README.md) | 简体中文

---

## 为什么需要这个

大模型面对复杂问题时，经常给一个笼统的答案。如果追问细节，它会编造。如果只搜一次，覆盖面不够。

DeepSearcher 做了三件事来解决这个问题：
- **问题拆解** — 把"XX技术有什么进展"拆成 N 个子问题，每个方向追问到底
- **循环搜索** — 不是搜一次就停。搜→读→反思→改词→再搜，发现缺了就补
- **质量门禁** — 最终输出要过六道检查：全面性、时效性、真实性，不达标就重来

---

## 快速开始

```bash
# 环境
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# CLI 模式
python -m deepsearcher "固态电池的最新突破有哪些"
python -m deepsearcher "解释一下 Transformer 的注意力机制" --max-turns 15

# Web 界面
python -m deepsearcher.server
# → http://localhost:8080
```

Web 前端需先构建：

```bash
cd vue && npm install && npm run build && cd ..
```

---

## 配置

编辑 `deepsearcher/config.py` 或设置环境变量：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `DEEPSEARCH_BASE_URL` | `http://localhost:56685/v1` | LLM 接口地址，兼容 OpenAI 格式 |
| `DEEPSEARCH_API_KEY` | *(内置)* | 替换为你自己的 key |
| `DEEPSEARCH_MODEL` | `openclaw` | 模型名 |
| `JINA_API_KEY` | *(空)* | 可选，启用 Jina Search |
| `MAX_TURNS` | 20 | 最大搜索循环轮数 |
| `TOKEN_BUDGET` | 100000 | 总 Token 预算 |

默认走本地 LLM 网关。改用 OpenAI 直连：

```bash
export DEEPSEARCH_BASE_URL="https://api.openai.com/v1"
export DEEPSEARCH_API_KEY="sk-..."
export DEEPSEARCH_MODEL="gpt-4o"
```

---

## 项目结构

```
DeepSearcher/
├── requirements.txt
├── deepsearcher/         # Python 包
│   ├── __main__.py      # `python -m deepsearcher "..."`
│   ├── cli.py           # CLI 逻辑
│   ├── agent.py         # LangGraph 搜索循环
│   ├── server.py        # Web API (FastAPI + SSE)
│   ├── config.py        # 配置
│   ├── models.py        # Pydantic 数据模型
│   └── tools/
│       ├── planner.py   # 问题拆解
│       ├── search.py    # DuckDuckGo / Jina 搜索
│       ├── read.py      # 网页内容提取
│       ├── evaluate.py  # 质量评估
│       └── rewrite.py   # 查询改写
│   └── utils/
│       ├── text_tools.py
│       ├── token_tracker.py
│       └── url_tools.py
├── vue/                 # Vue 3 前端
│   └── src/
└── results/             # 搜索历史缓存（git ignore）
```

---

## 设计权衡

- **Token 预算是全局的，不是按轮分配。** 一次大篇幅阅读会吃掉后面几轮的额度。`TOKEN_BUDGET` 设置大一点。
- **Beast Mode** 预留 15% 预算做兜底。如果前 85% 用完了还没找到满意答案，Beast Mode 用剩余信息生成最佳回答。
- **DuckDuckGo 免费但有限。** 做深度技术研究建议配 Jina Search 或换成自己的搜索后端。
- **SSE 推流默认配上 Vue 前端。** 如果你想用别的 UI，直接调 `/api/research` 接口就好。

---

## 许可

Apache 2.0
