# DeepThink Agent

流程：**Chat**（`deepseek-chat`）生成 **6～12 条**思考路径，每条含短标题 `path` 与「简洁但要详细」的阐明 `detail`；随后对**每条路径各调用一次** **R1**（`deepseek-reasoner`）；最后把所有路径上的 R1 推理与小结拼成上下文，再由 **Chat** 输出**唯一综合回答**。本地 Web 支持：

- **对比**：「单次纯 R1」与「多路径 × 多 R1 + Chat 综合」并排  
- **仅技术**：完整多阶段管线  
- **仅基线**：单次 R1  

## 快速开始

### 1. 准备环境

```bash
cd 深度-深度思考
python -m venv .venv
.venv\Scripts\activate
pip install -U pip
pip install -e .
```

### 2. 配置密钥

复制 `.env.example` 为 `.env`，填入你的 [DeepSeek API Key](https://platform.deepseek.com)：

```env
DEEPSEEK_API_KEY=sk-你的密钥
```

### 3. 启动

```bash
python main.py
```

浏览器将自动打开（若系统允许）`http://127.0.0.1:8765/`。在页面选择模式并输入问题即可。页面通过 `POST /api/run/stream` 以 **NDJSON 流** 接收事件；**对比模式**下左侧单次 R1 与右侧技术管线**并行**推进，技术侧各路径 R1 也**并行**调用（流式事件交错到达）。前端用 `static/vendor/` 内置的 **marked（UMD）+ DOMPurify** 做 Markdown 预览（避免仅依赖 CDN 时脚本加载失败、页面仍显示原始 `#`、`**` 等符号）。若需一次性 JSON，可调用 `POST /api/run`。

> 若未自动打开，请手动访问终端中打印的地址。

## 开发

```bash
pip install -e ".[dev]"
ruff check src tests
ruff format src tests
pytest
```

## 提示词设计要点

- **角色分离**：路径生成、R1 基线、R1+路径 使用独立 `system` 提示，避免指令混写导致权重不清。  
- **分隔符**：用户问题与候选路径分别包在 `<user_question>`、`<candidate_thinking_paths>` 中，降低串扰与注入面。  
- **可解析输出**：Chat 阶段使用 `response_format: json_object`，并在 system 中写死 JSON 契约（`paths[].path` / `paths[].reason`）。  
- **R1 参数**：不对 `deepseek-reasoner` 传入其不支持的采样参数（如 `temperature`）。  

详见 `src/deepthink_agent/prompts.py` 与 `docs/ARCHITECTURE.md`。

## 目录说明

| 路径 | 说明 |
|------|------|
| `main.py` | 启动 Uvicorn 与本地站点 |
| `src/deepthink_agent/` | 配置、提示词、API 客户端、业务编排、FastAPI |
| `static/` | 前端静态资源 |
| `tests/` | 单元测试 |
| `docs/` | 愿景与架构文档 |

## 许可证

MIT，见 `LICENSE`。

## 自检清单（维护者）

- [x] 无核心业务 TODO / 空实现  
- [x] README 可从零跑通主流程（需有效 API Key）  
- [x] `.env.example` 完整  
- [x] 测试可执行（健康检查 + 提示词/解析契约）  
- [x] CI：Ruff + Pytest  
- [x] 文档与代码结构一致（`docs/ARCHITECTURE.md`）  
