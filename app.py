from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

import httpx
from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ValidationError


BASE_DIR = Path(__file__).parent
STATIC_DIR = BASE_DIR / "static"
PROMPT_PATH = BASE_DIR / "prompts" / "system_prompt.txt"

app = FastAPI(title="6-Layer Agent Co-Creation Dialogue Prototype")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


INITIAL_STATE: Dict[str, Any] = {
    "schema_version": 2,
    "turn": 0,
    "world_state": {
        "scene_goal": "完成海边旧书屋春日共创会的第一轮筹备，让每个人的投入被温柔而准确地看见",
        "pressure": "温和但持续",
        "experiment_frame": "四人正在为旧书屋的周末共创会分配展区、署名、主持顺序和信息公开方式。",
        "active_fault_line": "公开认可、私人照顾、边界感三者无法同时被满足。",
        "scarce_resource": "下一步只有一个人的提案能被放进共创会开场环节。",
        "route_lean": "neutral",
        "recent_public_events": [],
    },
    "characters": {
        "A": {
            "affinity": 0,
            "distance": "stranger",
            "mask_on": True,
            "cracked_at": [],
            "emotions": ["维持表演状态", "对筹备规则有轻微不满"],
            "beliefs_about_player": [],
            "intention": "在本轮确立自己作为开场环节主导者的位置",
        },
        "B": {
            "affinity": 0,
            "distance": "stranger",
            "mask_on": True,
            "cracked_at": [],
            "emotions": ["观察中", "保持距离"],
            "beliefs_about_player": [],
            "intention": "等待玩家展示真实判断力",
        },
        "C": {
            "affinity": 0,
            "distance": "stranger",
            "mask_on": True,
            "cracked_at": [],
            "emotions": ["收集信息中", "尚未决定是否信任筹备节奏"],
            "beliefs_about_player": [],
            "intention": "通过提问建立对玩家的完整模型",
        },
    },
    "flags": {
        "A_ignored_twice": False,
        "A_curtain_fell": False,
        "B_overridden_once": False,
        "B_witnessed_real_choice": False,
        "C_excluded_from_info": False,
        "C_got_sincere_answer": False,
        "player_chose_efficiency_over_care": False,
        "player_showed_hesitation": False,
        "triangle_tension_visible": False,
    },
    "conversation_log": [],
}

DISTANCE_STAGES = ("stranger", "acquaintance", "guarded_close", "intimate")
ROUTE_LEANS = ("A_route", "B_route", "C_route", "collapse", "neutral")
MAX_CONVERSATION_LOG = 20
PIPELINE_CONVERSATION_LOG_LIMIT = 8


class ApiConfig(BaseModel):
    base_url: str
    api_key: str
    model: str
    disable_thinking: bool = True


class TestModelRequest(ApiConfig):
    pass


class TurnRequest(ApiConfig):
    player_input: str
    state: Optional[Dict[str, Any]] = None


class SuggestInputRequest(ApiConfig):
    state: Optional[Dict[str, Any]] = None


class SuggestedInput(BaseModel):
    player_input: str


class ActionParser(BaseModel):
    action_summary: str
    tone: str
    addressed_characters: List[str]
    public_facts: List[str]
    possible_social_meanings: List[str]
    action_validity: Literal["normal", "partially_valid", "invalid_but_interpretable"]


class CharacterMind(BaseModel):
    interpretation: str
    emotions: List[str]
    belief_updates: List[str]
    intention: str
    surface_attitude: str
    should_speak_next: bool


class CharacterMinds(BaseModel):
    A: CharacterMind
    B: CharacterMind
    C: CharacterMind


class SocialField(BaseModel):
    summary: str
    tension_points: List[str]
    relationship_vectors: List[str]
    suggested_pressure_point: str


class Director(BaseModel):
    next_scene_goal: str
    scene_beats: List[str]
    participating_characters: List[str]
    player_prompt: str


class DialogueLine(BaseModel):
    speaker: str
    emotion: str
    text: str


class Dialogue(BaseModel):
    narration: str
    lines: List[DialogueLine] = Field(min_length=1, max_length=3)
    prompt_to_player: str


class SubjectiveMemory(BaseModel):
    A: List[str]
    B: List[str]
    C: List[str]


class MemoryCurator(BaseModel):
    factual_memory: List[str]
    subjective_memory: SubjectiveMemory
    flags: Dict[str, bool]
    state_patch: Dict[str, Any]


class AgentOutput(BaseModel):
    action_parser: ActionParser
    character_minds: CharacterMinds
    social_field: SocialField
    director: Director
    dialogue: Dialogue
    memory_curator: MemoryCurator


class AgentOutputError(Exception):
    def __init__(self, message: str, raw_output: str = ""):
        super().__init__(message)
        self.raw_output = raw_output


def read_system_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")


def normalize_base_url(base_url: str) -> str:
    return base_url.strip().rstrip("/")


def merge_initial_state(default: Dict[str, Any], incoming: Dict[str, Any]) -> Dict[str, Any]:
    merged = deepcopy(default)
    for key, value in incoming.items():
        if key not in merged:
            continue
        if isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = merge_initial_state(merged[key], value)
        else:
            merged[key] = value
    return merged


def safe_state(state: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not isinstance(state, dict):
        return deepcopy(INITIAL_STATE)
    if state.get("schema_version") != INITIAL_STATE["schema_version"]:
        return deepcopy(INITIAL_STATE)
    return merge_initial_state(INITIAL_STATE, state)



def last_items(values: List[Any], limit: int) -> List[Any]:
    return values[-limit:] if len(values) > limit else values


def append_unique(existing: List[str], incoming: List[str], limit: int) -> List[str]:
    result = list(existing)
    for item in incoming:
        if item and item not in result:
            result.append(item)
    return last_items(result, limit)


def clamp_affinity(value: Any) -> int:
    try:
        numeric = int(value)
    except (TypeError, ValueError):
        return 0
    return max(-30, min(100, numeric))


def sanitize_character_patch(patch: Dict[str, Any]) -> Dict[str, Any]:
    sanitized = dict(patch)
    if "affinity" in sanitized:
        sanitized["affinity"] = clamp_affinity(sanitized["affinity"])
    if sanitized.get("distance") not in DISTANCE_STAGES:
        sanitized.pop("distance", None)
    if "mask_on" in sanitized:
        sanitized["mask_on"] = bool(sanitized["mask_on"])
    if "cracked_at" in sanitized:
        cracked_at = sanitized["cracked_at"]
        sanitized["cracked_at"] = cracked_at if isinstance(cracked_at, list) else []
    return sanitized


def apply_limited_patch(state: Dict[str, Any], patch: Dict[str, Any]) -> None:
    """Accept only simple top-level patch keys so model output cannot corrupt state shape."""
    if not isinstance(patch, dict):
        return
    world_patch = patch.get("world_state")
    if isinstance(world_patch, dict):
        if "route_lean" in world_patch and world_patch["route_lean"] not in ROUTE_LEANS:
            world_patch = dict(world_patch)
            world_patch.pop("route_lean", None)
        state.setdefault("world_state", {}).update(world_patch)

    character_patch = patch.get("characters")
    if isinstance(character_patch, dict):
        for key in ("A", "B", "C"):
            if isinstance(character_patch.get(key), dict):
                state.setdefault("characters", {}).setdefault(key, {}).update(
                    sanitize_character_patch(character_patch[key])
                )

    flag_patch = patch.get("flags")
    if isinstance(flag_patch, dict):
        flags = state.setdefault("flags", {})
        for key, value in flag_patch.items():
            if key in flags and value is True:
                flags[key] = True


def update_state(
    current_state: Dict[str, Any], player_input: str, agent_output: AgentOutput
) -> Dict[str, Any]:
    state = safe_state(current_state)
    output = agent_output.model_dump()
    memory = output["memory_curator"]
    minds = output["character_minds"]

    state["turn"] = int(state.get("turn", 0)) + 1
    events = state.setdefault("world_state", {}).setdefault("recent_public_events", [])
    events.extend(memory["factual_memory"])
    state["world_state"]["recent_public_events"] = last_items(events, 6)

    for character in ("A", "B", "C"):
        char_state = state.setdefault("characters", {}).setdefault(character, {})
        char_state["emotions"] = minds[character]["emotions"]
        char_state["intention"] = minds[character]["intention"]
        beliefs = char_state.setdefault("beliefs_about_player", [])
        beliefs.extend(memory["subjective_memory"][character])
        char_state["beliefs_about_player"] = last_items(beliefs, 6)

    flags = state.setdefault("flags", {})
    for key, value in memory.get("flags", {}).items():
        if key in flags and value is True:
            flags[key] = True

    state.setdefault("conversation_log", []).append(
        {
            "turn": state["turn"],
            "player_input": player_input,
            "dialogue": output["dialogue"],
        }
    )
    state["conversation_log"] = last_items(state["conversation_log"], MAX_CONVERSATION_LOG)
    apply_limited_patch(state, memory.get("state_patch", {}))
    return state


def build_context_for_pipeline(state: Dict[str, Any]) -> Dict[str, Any]:
    """Trim state sent to the main pipeline while preserving the useful trail."""
    trimmed = deepcopy(state)
    if "conversation_log" in trimmed:
        trimmed["conversation_log"] = last_items(
            trimmed["conversation_log"], PIPELINE_CONVERSATION_LOG_LIMIT
        )
    return trimmed


def build_user_prompt(
    player_input: str, state: Dict[str, Any], retry_note: Optional[str] = None
) -> str:
    context = build_context_for_pipeline(state)
    retry_block = ""
    if retry_note:
        retry_block = (
            "\n\n上一次输出不合法。请修复："
            f"\n{retry_note}"
            "\n这一次只返回合法 JSON，不要包含 Markdown 或解释。"
        )

    return (
        "请根据当前状态与玩家输入，运行 single-call 6 层 Agent pipeline。"
        "\n必须完整输出 action_parser、character_minds、social_field、director、dialogue、memory_curator。"
        "\n当前状态 JSON：\n"
        f"{json.dumps(context, ensure_ascii=False, indent=2)}"
        "\n\n玩家输入：\n"
        f"{player_input}"
        f"{retry_block}"
    )


def extract_json(raw: str) -> Dict[str, Any]:
    text = raw.strip()
    if text.startswith("```"):
        text = text.replace("```json", "```", 1).strip("` \n")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(text[start : end + 1])
        raise


async def post_chat_completion(
    config: ApiConfig,
    messages: List[Dict[str, str]],
    *,
    temperature: float = 0.7,
    use_response_format: bool = True,
) -> Dict[str, Any]:
    url = f"{normalize_base_url(config.base_url)}/chat/completions"
    headers = {
        "Authorization": f"Bearer {config.api_key}",
        "Content-Type": "application/json",
    }

    attempts = [
        (use_response_format, config.disable_thinking),
        (False, config.disable_thinking),
        (use_response_format, False),
        (False, False),
    ]
    seen_attempts = set()
    last_response: Optional[httpx.Response] = None

    async with httpx.AsyncClient(timeout=60) as client:
        for include_response_format, include_thinking in attempts:
            key = (include_response_format, include_thinking)
            if key in seen_attempts:
                continue
            seen_attempts.add(key)

            payload: Dict[str, Any] = {
                "model": config.model.strip(),
                "messages": messages,
                "temperature": temperature,
            }
            if include_response_format:
                payload["response_format"] = {"type": "json_object"}
            if include_thinking:
                payload["thinking"] = {"type": "disabled"}

            response = await client.post(url, headers=headers, json=payload)
            last_response = response
            if response.status_code < 400:
                return response.json()

            # Retry only likely parameter-compatibility failures. Auth, quota,
            # and server errors should surface directly.
            if response.status_code not in (400, 422):
                response.raise_for_status()

        assert last_response is not None
        last_response.raise_for_status()
        return last_response.json()


def get_message_content(response_json: Dict[str, Any]) -> str:
    try:
        content = response_json["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ValueError(f"Chat Completions response missing message content: {exc}") from exc
    if not isinstance(content, str):
        raise ValueError("Chat Completions message content is not a string")
    return content


def build_retry_note(exc: AgentOutputError) -> str:
    msg = str(exc)[:800]
    hints = []
    for field in ("dialogue", "memory_curator", "character_minds", "action_parser"):
        if field in msg:
            hints.append(field)
    hint_str = f"（问题可能出在：{', '.join(hints)}）" if hints else ""
    return f"{msg} {hint_str}".strip()


async def call_agent_once(
    config: ApiConfig,
    player_input: str,
    state: Dict[str, Any],
    retry_note: Optional[str] = None,
) -> tuple[AgentOutput, str]:
    messages = [
        {"role": "system", "content": read_system_prompt()},
        {"role": "user", "content": build_user_prompt(player_input, state, retry_note)},
    ]
    response_json = await post_chat_completion(config, messages, temperature=0.78)
    raw_output = get_message_content(response_json)
    try:
        parsed = extract_json(raw_output)
        return AgentOutput.model_validate(parsed), raw_output
    except (json.JSONDecodeError, ValidationError, ValueError) as exc:
        raise AgentOutputError(f"{type(exc).__name__}: {exc}", raw_output) from exc


async def run_single_call_pipeline(
    config: ApiConfig, player_input: str, state: Dict[str, Any]
) -> tuple[AgentOutput, str]:
    try:
        return await call_agent_once(config, player_input, state)
    except AgentOutputError as first_error:
        retry_note = build_retry_note(first_error)
        return await call_agent_once(config, player_input, state, retry_note)


async def run_step_by_step_pipeline(
    config: ApiConfig, player_input: str, state: Dict[str, Any]
) -> tuple[AgentOutput, str]:
    # Reserved for a future six-call implementation. The first prototype keeps
    # one request so behavior is easier to inspect and compare.
    return await run_single_call_pipeline(config, player_input, state)


async def generate_suggested_input(config: ApiConfig, state: Dict[str, Any]) -> str:
    context = {
        "turn": state.get("turn", 0),
        "route_lean": state.get("world_state", {}).get("route_lean", "neutral"),
        "characters": {
            key: {
                "distance": value.get("distance"),
                "mask_on": value.get("mask_on"),
                "affinity": value.get("affinity"),
                "intention": value.get("intention"),
            }
            for key, value in state.get("characters", {}).items()
            if isinstance(value, dict)
        },
        "flags": state.get("flags", {}),
        "recent_events": state.get("world_state", {}).get("recent_public_events", [])[-3:],
    }

    messages = [
        {
            "role": "system",
            "content": (
                "你在模拟一个人在旧书屋共创会里，刚刚有了一个行动冲动的那一刻。"
                "只输出合法 JSON，不要输出 Markdown，不要解释。"
                "这个人不会用社交策略的眼光想问题，但他的选择会自然地照顾到某人、忽视某人、或在某人心里留下一个问号。"
                "这个行动必须让下一轮剧情有明确可回应的变化，而不是只有气氛或暧昧细节。"
                "不要替玩家做重大决定。不要新增地点、组织、突然离场或激烈冲突。"
            ),
        },
        {
            "role": "user",
            "content": (
                "根据当前状态，写出玩家下一轮最可能自然做出的行动，一句话。"
                "这句话必须推进一个具体的筹备事项，让角色下一轮能围绕它继续说话或行动。\n\n"
                "这句话应该像一个人在安静的书屋里，忽然动了一下--"
                "可能是把什么东西递过去，可能是在谁的便签上多写了一个字，"
                "可能是回答了一个问题但声音刚好只有某人听到，"
                "可能是在讨论结束时突然把椅子往某人那边挪了一点。"
                "但这个动作要顺手改变一个真实安排，例如开场顺序、署名、留言展示范围、朗读人选、旧物摆放、谁保管某张便签。\n\n"
                "要求：\n"
                "- 40 到 80 个中文字符，一句话，写玩家的行动，不写旁白，不写角色反应\n"
                "- 有具体的物理动作或语言，不是心理活动，不是情绪表达\n"
                "- 必须明确推进一个筹备事项：安排、分配、确认、改动、暂缓或交给某人处理\n"
                "- 有一个细节是只有某一个人能接收到的--但不直接说是给谁的\n"
                "- 读起来像是这件事本来就会发生，不像是为了推进剧情刻意设计的\n"
                "- 不要只写递东西、移动椅子、看向某人、写下无意义短句；动作之后必须留下一个下一轮要处理的结果\n"
                "- 语气不要「任务式」，不要出现“我决定”“我提议”“我宣布”\n"
                "- 禁止告白、道歉万能句、离开、战斗\n\n"
                "可以使用的场景元素：书签、便签、茶杯、傍晚窗光、朗读、手写、靠窗座位、旧物、灯、气味、安静、某人的名字。\n\n"
                "当前状态：\n"
                f"{json.dumps(context, ensure_ascii=False, indent=2)}\n\n"
                '\n输出格式：{"player_input":"..."}'
            ),
        },
    ]
    response_json = await post_chat_completion(
        config, messages, temperature=1.05, use_response_format=True
    )
    raw_output = get_message_content(response_json)
    parsed = extract_json(raw_output)
    suggestion = SuggestedInput.model_validate(parsed)
    return suggestion.player_input.strip()


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.post("/api/test_model")
async def test_model(request: TestModelRequest) -> JSONResponse:
    try:
        messages = [
            {"role": "system", "content": "只返回一个很短的 JSON 对象。"},
            {"role": "user", "content": '{"ping":"请回复 pong"}'},
        ]
        response_json = await post_chat_completion(request, messages, temperature=0.1)
        return JSONResponse(
            {
                "success": True,
                "message": "模型连接成功。",
                "sample": get_message_content(response_json)[:500],
            }
        )
    except Exception as exc:
        return JSONResponse(
            {"success": False, "error": f"{type(exc).__name__}: {exc}"},
            status_code=200,
        )


@app.post("/api/turn")
async def turn(request: TurnRequest) -> JSONResponse:
    player_input = request.player_input.strip()
    if not player_input:
        return JSONResponse({"ok": False, "error": "player_input 不能为空。"})

    state = safe_state(request.state)
    raw_output = ""
    try:
        agent_output, raw_output = await run_single_call_pipeline(request, player_input, state)
        new_state = update_state(state, player_input, agent_output)
        return JSONResponse(
            {
                "ok": True,
                "agent_output": agent_output.model_dump(),
                "new_state": new_state,
            }
        )
    except AgentOutputError as exc:
        return JSONResponse(
            {
                "ok": False,
                "error": str(exc),
                "raw_output": exc.raw_output,
            }
        )
    except Exception as exc:
        return JSONResponse(
            {
                "ok": False,
                "error": f"{type(exc).__name__}: {exc}",
                "raw_output": raw_output,
            }
        )


@app.post("/api/suggest_input")
async def suggest_input(request: SuggestInputRequest) -> JSONResponse:
    try:
        state = safe_state(request.state)
        player_input = await generate_suggested_input(request, state)
        if not player_input:
            return JSONResponse({"ok": False, "error": "模型返回了空建议。"})
        return JSONResponse({"ok": True, "player_input": player_input})
    except Exception as exc:
        return JSONResponse(
            {"ok": False, "error": f"{type(exc).__name__}: {exc}"},
            status_code=200,
        )


@app.post("/api/reset")
async def reset() -> Dict[str, Any]:
    return deepcopy(INITIAL_STATE)
