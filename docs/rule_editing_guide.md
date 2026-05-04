# 规则修改指南

这份文档说明项目中哪些文本可以定义背景、人物性格、场景冲突和自动玩家输入，以及这些文本需要遵守的固定格式。

## 文件分工

- `prompts/system_prompt.txt`：最主要的规则文件。控制世界观、人物性格、导演原则、硬约束和模型必须输出的 JSON 结构。
- `app.py`：后端状态、接口 schema、自动玩家输入生成规则。修改角色数量、JSON 字段、初始状态时需要同步这里。
- `static/main.js`：前端保存的初始状态。它要和 `app.py` 里的 `INITIAL_STATE` 保持一致，否则重置或旧浏览器状态可能显示不同设定。
- `static/index.html`：页面标题、按钮文案、输入框示例。
- `README.md`：项目说明和验收示例。

## 最常改的规则

### 背景和玩法定位

修改 `prompts/system_prompt.txt` 的这些段落：

```text
全局场景设定：
...

场景默认张力：
- ...
- ...
- ...
```

建议写法：

- 第一段说明玩家、角色、当前场景和基本压力。
- 第二段说明这个原型的核心体验，例如温和协作、亲密关系、群像误读、共创会筹备等。
- `场景默认张力` 用项目符号列出 3 到 6 条稳定规则。

不要在这里写固定剧情结局。更适合写“会反复出现的压力来源”，例如信息不对称、公开署名、开场名额、边界被试探。

### 人物性格

修改 `prompts/system_prompt.txt` 的 `固定角色` 段落。当前角色块使用固定文本格式：

```text
A：
- traits: ...
- desire: ...
- fear: ...
- conflict_axis: ...
- speech_style: ...
```

字段含义：

- `traits`：外显性格和行为习惯。
- `desire`：这个角色想从玩家或团队中得到什么。
- `fear`：这个角色最怕被怎样对待。
- `conflict_axis`：这个角色制造张力的核心矛盾。
- `speech_style`：台词风格，包含句长、语气、是否直白、是否常用反问等。

推荐每个角色都保留这 5 个字段。它们不是后端强校验字段，但 prompt 会依赖这种稳定格式来生成更一致的角色。

### 导演原则

修改 `prompts/system_prompt.txt` 的 `导演原则` 段落：

```text
导演原则：
- 每轮必须制造一个“微型不可兼得”：...
- dialogue 里的角色反应要...
- prompt_to_player 要...
```

这里适合定义“每轮怎样推进”。例如：

- 每轮只推进一个小事件。
- 玩家不能一次完美满足所有人。
- 谁沉默、谁转移话题、谁提出条件。
- 下一步提示要逼近一个具体选择。

如果你觉得剧情太平，就强化这里。如果你觉得剧情太失控，就收紧这里。

### 硬约束

修改 `prompts/system_prompt.txt` 的 `硬约束` 段落：

```text
硬约束：
1. ...
2. ...
```

这里适合写模型绝对不能违反的规则，例如：

- 每轮最多几句台词。
- 旁白和台词字数范围。
- 不得新增地点、组织、死亡、暴力升级。
- 角色不能知道不可见信息。
- 输出必须是合法 JSON。

这部分建议使用编号列表。越靠后的规则不一定越弱，所以请把关键限制写清楚，不要只靠语气暗示。

### 自动玩家输入

修改 `app.py` 里的 `generate_suggested_input(...)`。重点是这个 system/user prompt：

```python
"你在模拟一个人在旧书屋共创会里，刚刚有了一个行动冲动的那一刻。"
...
"要求：40 到 80 个中文字符；有具体的物理动作或语言；必须明确推进一个筹备事项；有一个细节是只有某一个人能接收到的；..."
```

这里控制“AI 生成推进输入”按钮的行为。适合定义：

- 玩家输入的字数范围。
- 是否必须包含具体动作、物件、位置或一句自然说出口的话。
- 是否必须推进一个具体筹备事项，例如开场顺序、署名、留言展示范围、朗读人选或旧物摆放。
- 是否要让空气里留下只被某个人接收到的细节。
- 是否需要避免任务式表态，例如“我决定”“我提议”“我宣布”。
- 禁止生成哪些输入，例如告白、离场、战斗、重大决定。

固定输出格式是：

```json
{"player_input":"..."}
```

如果修改这个 JSON 字段名，需要同步 `SuggestedInput` 这个 Pydantic 模型和前端读取逻辑。一般不建议改字段名。

## 初始状态

初始状态需要同步两处：

- `app.py` 的 `INITIAL_STATE`
- `static/main.js` 的 `INITIAL_STATE`

当前结构大致是：

```json
{
  "schema_version": 2,
  "turn": 0,
  "world_state": {
    "scene_goal": "...",
    "pressure": "...",
    "experiment_frame": "...",
    "active_fault_line": "...",
    "scarce_resource": "...",
    "route_lean": "neutral",
    "recent_public_events": []
  },
  "characters": {
    "A": {
      "affinity": 0,
      "distance": "stranger",
      "mask_on": true,
      "cracked_at": [],
      "emotions": ["...", "..."],
      "beliefs_about_player": [],
      "intention": "..."
    }
  },
  "flags": {
    "A_ignored_twice": false,
    "A_curtain_fell": false,
    "B_overridden_once": false,
    "B_witnessed_real_choice": false,
    "C_excluded_from_info": false,
    "C_got_sincere_answer": false,
    "player_chose_efficiency_over_care": false,
    "player_showed_hesitation": false,
    "triangle_tension_visible": false
  },
  "conversation_log": []
}
```

可安全修改的部分：

- `world_state.scene_goal`
- `world_state.pressure`
- `world_state.experiment_frame`
- `world_state.active_fault_line`
- `world_state.scarce_resource`
- `world_state.route_lean`
- 每个角色的 `affinity`
- 每个角色的 `distance`
- 每个角色的 `mask_on`
- 每个角色的 `emotions`
- 每个角色的 `intention`

不建议随意改的部分：

- `turn`
- `schema_version`
- `recent_public_events`
- `beliefs_about_player`
- `flags`
- `conversation_log`

这些字段由程序运行时维护。

## 输出 JSON 固定格式

`prompts/system_prompt.txt` 末尾的 JSON 示例必须和 `app.py` 里的 Pydantic schema 一致。当前必须输出：

```text
action_parser
character_minds
social_field
director
dialogue
memory_curator
```

如果只改背景、人物、台词风格、冲突强度，不要改这个 JSON 结构。

如果要新增字段，需要同步修改：

- `prompts/system_prompt.txt` 末尾 JSON 示例
- `app.py` 里对应的 `BaseModel`
- `static/main.js` 里展示或读取该字段的逻辑，如果前端需要使用它

如果要把三名角色改成更多或更少角色，需要同步修改：

- `prompts/system_prompt.txt` 的 `固定角色`
- `prompts/system_prompt.txt` 末尾 `character_minds` 和 `subjective_memory`
- `app.py` 的 `INITIAL_STATE`
- `app.py` 的 `CharacterMinds`
- `app.py` 的 `SubjectiveMemory`
- `app.py` 里遍历 `("A", "B", "C")` 的地方
- `static/main.js` 的 `INITIAL_STATE`

这是结构性修改，比普通规则调参更容易出错。

## 推荐修改流程

1. 先改 `prompts/system_prompt.txt`，只调整背景、角色和导演原则。
2. 如果第一轮状态也要变化，同步改 `app.py` 和 `static/main.js` 的 `INITIAL_STATE`。
3. 如果页面示例不符合新设定，改 `static/index.html`。
4. 如果自动输入不够会推进事件，改 `app.py` 的 `generate_suggested_input(...)`。
5. 启动项目后测试 3 到 5 轮，观察 JSON 中的 `social_field`、`flags`、`route_lean` 和 `character_minds` 是否继承前文。

## 小型模板

可以用这个模板替换或扩展角色：

```text
角色名：
- traits: 外显性格；行为习惯；别人容易误解他的地方
- desire: 他真正想被怎样对待；他希望玩家承认什么
- fear: 他最怕被怎样使用、忽视或定义
- conflict_axis: 他稳定制造的关系矛盾。写成“X 与 Y”
- speech_style: 句长、语气、是否反问、是否绕弯、是否直接表达情绪
```

可以用这个模板扩展场景压力：

```text
场景默认张力：
- 稀缺资源：这一轮只有一种方案、一个开场名额或一次公开署名机会。
- 信息不对称：某人知道事实但不确定是否该公开。
- 温和压力：每个人都想让共创会顺利，但对“被看见”的需求不一样。
- 边界试探：玩家可以请求帮助，但请求方式会影响角色是否感到被尊重。
```
