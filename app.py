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

app = FastAPI(title="6-Layer Agent Otome Dialogue Prototype")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


INITIAL_STATE: Dict[str, Any] = {
    "turn": 0,
    "world_state": {
        "scene_goal": "维持协作并推进当前项目",
        "pressure": "中等",
        "recent_public_events": [],
    },
    "characters": {
        "A": {
            "emotions": ["克制", "观察"],
            "beliefs_about_player": [],
            "intention": "观察玩家如何处理协作压力",
        },
        "B": {
            "emotions": ["好奇", "试探"],
            "beliefs_about_player": [],
            "intention": "用轟松方式接近玩家",
        },
        "C": {
            "emotions": ["安静", "警觉"],
            "beliefs_about_player": [],
            "intention": "先观察，再用行动提供帮助",
        },
    },
    "open_threads": [],
    "conversation_log": [],
}


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
    open_threads: List[str]
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


def safe_state(state: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not isinstance(state, dict):
        return deepcopy(INITIAL_STATE)
    merged = deepcopy(INITIAL_STATE)
    for key, value in state.items():
        if key in merged:
            merged[key] = value
    return merged


def last_items(values: List[Any], limit: int) -> List[Any]:
    return values[-limit:] if len(values) > limit else values


def append_unique(existing: List[str], incoming: List[str], limit: int) -> List[str]:
    result = list(existing)
    for item in incoming:
        if item and item not in result:
            result.append(item)
    return last_items(result, limit)


def apply_limited_patch(state: Dict[str, Any], patch: Dict[str, Any]) -> None:
    """Accept only simple top-level patch keys so model output cannot corrupt state shape."""
    if not isinstance(patch, dict):
        return
    world_patch = patch.get("world_state")
    if isinstance(world_patch, dict):
        state.setdefault("world_state", {}).update(world_patch)

    character_patch = patch.get("characters")
    if isinstance(character_patch, dict):
        for key in ("A", "B", "C"):
            if isinstance(character_patch.get(key), dict):
                state.setdefault("characters", {}).setdefault(key, {}).update(character_patch[key])


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

    state["open_threads"] = append_unique(
        state.get("open_threads", []), memory["open_threads"], 6
    )

    state.setdefault("conversation_log", []).append(
        {
            "turn": state["turn"],
            "player_input": player_input,
            "dialogue": output["dialogue"],
        }
    )
    state["conversation_log"] = last_items(state["conversation_log"], 10)
    apply_limited_patch(state, memory.get("state_patch", {}))
    return state


def build_user_prompt(
    player_input: str, state: Dict[str, Any], retry_note: Optional[str] = None
) -> str:
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
        f"{json.dumps(state, ensure_ascii=False, indent=2)}"
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
    response_json = await post_chat_completion(config, messages, temperature=0.7)
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
        retry_note = f"{type(first_error).__name__}: {str(first_error)[:1200]}"
        return await call_agent_once(config, player_input, state, retry_note)


async def run_step_by_step_pipeline(
    config: ApiConfig, player_input: str, state: Dict[str, Any]
) -> tuple[AgentOutput, str]:
    # Reserved for a future six-call implementation. The first prototype keeps
    # one request so behavior is easier to inspect and compare.
    return await run_single_call_pipeline(config, player_input, state)


async def generate_suggested_input(config: ApiConfig, state: Dict[str, Any]) -> str:
    messages = [
        {
            "role": "system",
            "content": (
                "你是一个受约束的玩家输入建议器。只输出合法 JSON，不要输出 Markdown。"
                "不要替玩家做重大决定，不要新增地点、组织、阴谋、战斗、死亡或突然离场。"
            ),
        },
        {
            "role": "user",
            "content": (
                "请根据当前状态，生成一句适合下一轮输入框使用的中文玩家行动。"
                "要求：一句话，25 到 80 个中文字符；只推进一个小事件；可以同时照顾 A、B、C 的不同感受；"
                "不要写角色台词，不要写旁白。"
                "\n当前状态 JSON：\n"
                f"{json.dumps(state, ensure_ascii=False, indent=2)}"
                '\n输出格式：{"player_input":"..."}'
            ),
        },
    ]
    response_json = await post_chat_completion(config, messages, temperature=0.8)
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
