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

DeepSearcher 默认使用 OpenAI 协议，通过**四级优先级**自动解析配置：

| 优先级 | 方式 | 说明 |
|--------|------|------|
| 1 | `DEEPSEARCH_*` 环境变量 | 直接覆盖，优先级最高 |
| 2 | `local_config.json` | 项目根目录，gitignore 不提交 |
| 3 | `OPENAI_*` 标准环境变量 | 兼容 OpenAI SDK 习惯 |
| 4 | 默认值 | `https://api.openai.com/v1` / `gpt-4o` |

### 方式一：用 OpenAI（零配置）

只需要设置标准环境变量：

```bash
export OPENAI_API_KEY="sk-..."
```

如果需要自定义 base_url 或模型：

```bash
export OPENAI_BASE_URL="https://api.openai.com/v1"
export OPENAI_MODEL="gpt-4o"        # 可选，默认 gpt-4o
```

### 方式二：用自己的网关（local_config.json）

复制模板文件并修改：

```bash
cp local_config.json.example local_config.json
# 编辑 local_config.json，改成自己的地址和模型
```

```json
{
  "base_url": "http://localhost:8080/v1",
  "api_key": "sk-***",
  "model": "gpt-4o"
}
```

`local_config.json` 已加入 `.gitignore`，不会泄露到仓库。

### 环境变量参考

| 变量 | 说明 |
|------|------|
| `OPENAI_API_KEY` | API 密钥 |
| `OPENAI_BASE_URL` | API 地址，兼容 OpenAI 格式 |
| `DEEPSEARCH_API_KEY` | 覆盖 OPENAI_API_KEY |
| `DEEPSEARCH_BASE_URL` | 覆盖 OPENAI_BASE_URL |
| `DEEPSEARCH_MODEL` | 模型名，默认 `gpt-4o` |
| `JINA_API_KEY` | 可选，启用 Jina Search |
| `MAX_TURNS` | 最大搜索循环轮数，默认 20 |
| `TOKEN_BUDGET` | 总 Token 预算，默认 100000 |

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
