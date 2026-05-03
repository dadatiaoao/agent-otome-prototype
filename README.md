# 6 层 Agent 社交实验对话原型

这是一个最小可运行的本地 Web 实验品，用来验证“6 层 Agent 架构驱动的社交实验 / 群像对话原型”。它保留亲密关系张力，但目标不是单纯攻略角色，而是观察玩家在高压协作中如何分配信任、责任、可见性和边界。

核心玩法：玩家输入一句自然语言行为后，后端用 OpenAI-compatible Chat Completions API 生成三名角色对该行为的主观理解，并基于这些理解生成下一轮可见对话。连续输入 3 到 5 轮后，可以观察误解、意图、情绪、开放线索和“被测试感”是否被继承。

当前默认场景是一场不完全透明的协作观察实验：A、B、C 都知道表现会被记录，却不确定评价标准是效率、诚实、控制力、照顾他人，还是冲突中暴露的真实偏好。每轮会尽量制造一个小型不可兼得的压力点，例如公开采用谁的方案、谁承担可见责任、是否共享敏感信息、如何处理被当成工具的感受。

玩家可见剧情区会显示最近 10 轮完整上下文，包括每轮玩家输入、旁白、角色台词和下一步提示。

## 启动方式

```bash
pip install -r requirements.txt
uvicorn app:app --reload
```

浏览器访问：

```text
http://127.0.0.1:8000
```

## API Key 配置

页面顶部提供三个配置输入框：

- Base URL，DeepSeek 推荐使用 `https://api.deepseek.com`
- API Key
- Model Name，例如 `deepseek-v4-flash`

点击“保存配置”后，配置会写入浏览器 `localStorage`。API Key 会随请求发送给本地 FastAPI 后端，但后端不会把 API Key 写入磁盘。

页面默认勾选“关闭 DeepSeek 思考模式”。勾选后，后端会在 Chat Completions 请求体中加入：

```json
{"thinking": {"type": "disabled"}}
```

玩家输入区的“AI 生成推进输入”会读取当前状态，并调用同一个 OpenAI-compatible API 生成一句可编辑的玩家行动建议。它不会推进回合，也不会修改状态。新建议会优先包含具体动作和可被误解或质疑的取舍，避免只写安抚或完美照顾所有人的输入。

## API 兼容性

后端只调用 OpenAI-compatible Chat Completions API：

```text
POST {base_url}/chat/completions
```

默认请求会带上：

```json
{"response_format": {"type": "json_object"}}
```

如果兼容接口不支持 `response_format` 并返回错误，后端会自动移除该字段再请求一次。

如果兼容接口不支持 DeepSeek 的 `thinking` 字段，后端也会自动移除该字段再请求一次。使用 DeepSeek V4 Flash 时建议保持“关闭 DeepSeek 思考模式”开启。

## 6 层 Agent 架构

当前默认实现是 single-call pipeline：一次模型调用输出完整 JSON。代码中保留了以下函数位置：

- `run_single_call_pipeline(...)`
- `run_step_by_step_pipeline(...)`

六层结构如下：

1. `action_parser`：解析玩家输入行为。
2. `character_minds`：A、B、C 三名角色分别形成主观解释。
3. `social_field`：分析三人之间的关系张力。
4. `director`：决定下一幕如何推进。
5. `dialogue`：生成玩家可见旁白、角色台词和下一步提示。
6. `memory_curator`：整理事实记忆、主观记忆、开放线索和状态补丁。

系统 prompt 位于 `prompts/system_prompt.txt`。后端 schema 与校验逻辑位于 `app.py`。

## 规则修改

背景、人物性格、导演原则、硬约束、自动玩家输入和固定 JSON 格式的修改方法见：

- [`docs/rule_editing_guide.md`](docs/rule_editing_guide.md)

## 常见问题

### 模型不支持 response_format

后端会在第一次请求失败后自动移除 `response_format` 再重试一次。如果仍失败，页面会显示错误。

### 如何关闭 DeepSeek 深度思考模式

保持 API 配置区的“关闭 DeepSeek 思考模式”勾选即可。后端会发送 `thinking: {"type": "disabled"}`。如果你切换到其它 OpenAI-compatible 服务，而该服务不支持这个字段，后端会自动降级移除它。

### JSON 输出失败

后端使用 Pydantic 对模型输出做基本校验。如果 JSON 解析失败或 schema 不符合要求，会自动重试一次，并在重试 prompt 中说明上一次输出不合法。仍失败时，前端开发者面板会显示错误信息和原始输出，方便调试。

### API Key 会保存到哪里

API Key 只保存在浏览器 `localStorage` 中，并随请求发送到本地后端。后端不会把 API Key 写入磁盘。导出的 `debug.json` 会排除 API Key。

## 最小验收方法

1. 打开 `http://127.0.0.1:8000`。
2. 填入 Base URL、API Key、Model Name，并保持“关闭 DeepSeek 思考模式”勾选。
3. 点击“测试模型”，确认连接成功。
4. 输入：`我公开采用 A 的方案，但要求 B 记录反对意见，并请 C 只补充他确认过的证据。`
5. 也可以先点击“AI 生成推进输入”，让模型填入一句可编辑的默认行动。
6. 点击“发送”。
7. 页面应显示包含前文的可见剧情上下文：每轮玩家输入、简短旁白、1 到 3 句角色台词和下一步提示。
8. 展开开发者面板，确认存在 `action_parser`、`character_minds`、`social_field`、`director`、`dialogue`、`memory_curator` 六层 JSON。
9. 观察当前状态 JSON 是否更新。
10. 再输入第二轮，观察上一轮产生的 A 的被测试感、B 对自身权重的试探、C 对边界和归因的警觉等内容是否被后续继承。
