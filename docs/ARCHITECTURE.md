# 架构说明

## 技术栈

- Python 3.11+、FastAPI、Uvicorn  
- OpenAI 兼容客户端 → DeepSeek `deepseek-chat` / `deepseek-reasoner`  
- 前端：原生 HTML/CSS/JS，`POST /api/run/stream` 返回 **NDJSON** 事件流  
- Markdown：`static/vendor/` 内置 **marked（UMD）** 与 **DOMPurify**  

## 技术管线（顺序）

1. **问题分类（Chat，JSON）**  
   读取用户问题，输出 `domain_type`、`difficulty`、`subcategory`、`structure_type`、`thinking_stance` 等字符串字段。提示词要求**不复述**用户原文可识别细节，只给抽象画像与思考定调。

2. **思考路径生成（Chat，JSON）**  
   输入 `<problem_profile>`（由上一步字段排版）+ `<user_question>`。路径须为**元认知 / 过程链**（自检问句、先后步骤），避免空泛话题标签。

3. **分路径 R1（并行流式）**  
   每条路径独立 `deepseek-reasoner` 流；多路经 `asyncio` 任务写入同一队列，事件交错下发。

4. **综合回答（Chat，流式）**  
   汇总各路径 R1 推理与小结，生成唯一用户可见终稿。

## 对比模式

`merge_async_dict_streams` 同时合并：

- **基线流**：单次 R1 流式 → `branch_end`  
- **技术流**：`paths_loading` → `classifying` → `classification` 事件 → `paths` → 并行路径 R1 → `synthesis_*` → `branch_end`  

两条流事件顺序**任意交错**。

## 前端交互约定

- **基线**：默认折叠「深度思考」区块，仅回答区直接可见（用户点击展开 CoT）。  
- **技术侧**：`classification`、`paths` 列表包在 `<details>` 内默认折叠；每条路径的「阐明 + R1 推理」包在内层 `<details>`；**小结与综合回答**默认外露。综合开始后为技术卡片加 `ds-tech-results-priority`，用 flex `order` 将综合回答提前，减少滚动。  

## 目录

| 路径 | 职责 |
|------|------|
| `main.py` | 启动服务 |
| `src/deepthink_agent/prompts.py` | 分类、路径、R1、综合等提示词 |
| `src/deepthink_agent/services.py` | 分类解析、路径解析、编排、非流式 API |
| `src/deepthink_agent/streaming.py` | 流式事件与并行合并 |
| `src/deepthink_agent/web/app.py` | 路由与静态资源 |
| `static/app.js` | 流解析、Markdown、折叠 UI |
| `static/vendor/` | marked、DOMPurify |

## 横切

- 密钥仅环境变量；不对 `deepseek-reasoner` 传不支持的采样参数。  
- 错误以 JSON / NDJSON `error` 事件返回明确信息。  

## 质量

- `ruff`、`pytest`；详见 `README.md` 开发小节。
