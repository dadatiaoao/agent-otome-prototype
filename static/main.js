const INITIAL_STATE = {
  schema_version: 2,
  turn: 0,
  world_state: {
    scene_goal: "完成海边旧书屋春日共创会的第一轮筹备，让每个人的投入被温柔而准确地看见",
    pressure: "温和但持续",
    experiment_frame: "四人正在为旧书屋的周末共创会分配展区、署名、主持顺序和信息公开方式。",
    active_fault_line: "公开认可、私人照顾、边界感三者无法同时被满足。",
    scarce_resource: "下一步只有一个人的提案能被放进共创会开场环节。",
    route_lean: "neutral",
    recent_public_events: [],
  },
  characters: {
    A: {
      affinity: 0,
      distance: "stranger",
      mask_on: true,
      cracked_at: [],
      emotions: ["维持表演状态", "对筹备规则有轻微不满"],
      beliefs_about_player: [],
      intention: "在本轮确立自己作为开场环节主导者的位置",
    },
    B: {
      affinity: 0,
      distance: "stranger",
      mask_on: true,
      cracked_at: [],
      emotions: ["观察中", "保持距离"],
      beliefs_about_player: [],
      intention: "等待玩家展示真实判断力",
    },
    C: {
      affinity: 0,
      distance: "stranger",
      mask_on: true,
      cracked_at: [],
      emotions: ["收集信息中", "尚未决定是否信任筹备节奏"],
      beliefs_about_player: [],
      intention: "通过提问建立对玩家的完整模型",
    },
  },
  flags: {
    A_ignored_twice: false,
    A_curtain_fell: false,
    B_overridden_once: false,
    B_witnessed_real_choice: false,
    C_excluded_from_info: false,
    C_got_sincere_answer: false,
    player_chose_efficiency_over_care: false,
    player_showed_hesitation: false,
    triangle_tension_visible: false,
  },
  conversation_log: [],
};

const els = {
  baseUrl: document.querySelector("#baseUrl"),
  apiKey: document.querySelector("#apiKey"),
  modelName: document.querySelector("#modelName"),
  disableThinking: document.querySelector("#disableThinking"),
  saveConfigBtn: document.querySelector("#saveConfigBtn"),
  testModelBtn: document.querySelector("#testModelBtn"),
  configStatus: document.querySelector("#configStatus"),
  playerInput: document.querySelector("#playerInput"),
  suggestInputBtn: document.querySelector("#suggestInputBtn"),
  sendBtn: document.querySelector("#sendBtn"),
  resetBtn: document.querySelector("#resetBtn"),
  exportBtn: document.querySelector("#exportBtn"),
  turnStatus: document.querySelector("#turnStatus"),
  story: document.querySelector("#story"),
  agentOutput: document.querySelector("#agentOutput"),
  stateOutput: document.querySelector("#stateOutput"),
};

let state = loadState();
let lastAgentOutput = null;

function clone(value) {
  return JSON.parse(JSON.stringify(value));
}

function mergeInitialState(defaultState, savedState) {
  const merged = clone(defaultState);
  if (!savedState || typeof savedState !== "object") {
    return merged;
  }
  Object.entries(savedState).forEach(([key, value]) => {
    if (!(key in merged)) {
      return;
    }
    if (
      merged[key] &&
      value &&
      typeof merged[key] === "object" &&
      !Array.isArray(merged[key]) &&
      typeof value === "object" &&
      !Array.isArray(value)
    ) {
      merged[key] = mergeInitialState(merged[key], value);
    } else {
      merged[key] = value;
    }
  });
  return merged;
}

function loadConfig() {
  const saved = JSON.parse(localStorage.getItem("api_config") || "{}");
  return {
    base_url: saved.base_url || "https://api.deepseek.com",
    api_key: saved.api_key || "",
    model: saved.model || "deepseek-v4-flash",
    disable_thinking: saved.disable_thinking !== false,
  };
}

function saveConfig() {
  const config = readConfig();
  localStorage.setItem("api_config", JSON.stringify(config));
  setStatus(els.configStatus, "配置已保存。", "ok");
}

function readConfig() {
  return {
    base_url: els.baseUrl.value.trim(),
    api_key: els.apiKey.value.trim(),
    model: els.modelName.value.trim(),
    disable_thinking: els.disableThinking.checked,
  };
}

function loadState() {
  try {
    const saved = JSON.parse(localStorage.getItem("state") || "null");
    if (saved && saved.schema_version !== INITIAL_STATE.schema_version) {
      return clone(INITIAL_STATE);
    }
    return mergeInitialState(INITIAL_STATE, saved);
  } catch {
    return clone(INITIAL_STATE);
  }
}

function saveState() {
  localStorage.setItem("state", JSON.stringify(state));
}

function setStatus(el, text, kind = "") {
  el.textContent = text;
  el.className = `status ${kind}`.trim();
}

function renderState() {
  els.stateOutput.textContent = JSON.stringify(state, null, 2);
}

function renderAgentOutput(output) {
  els.agentOutput.textContent = JSON.stringify(output || {}, null, 2);
}

function renderDialogue(dialogue) {
  const lines = (dialogue.lines || [])
    .map(
      (line) => `
        <div class="line">
          <span class="speaker">${escapeHtml(line.speaker || "")}</span>
          <span class="emotion">（${escapeHtml(line.emotion || "")}）</span>
          ${escapeHtml(line.text || "")}
        </div>
      `
    )
    .join("");

  return `
    <p class="narration">${escapeHtml(dialogue.narration || "")}</p>
    ${lines}
    <p class="prompt"><strong>下一步：</strong>${escapeHtml(dialogue.prompt_to_player || "")}</p>
  `;
}

function renderStory() {
  const log = Array.isArray(state.conversation_log) ? state.conversation_log : [];
  if (log.length === 0) {
    els.story.innerHTML =
      '<p class="muted">尚未开始。输入一轮行动后，这里会显示旁白、角色台词和下一步提示。</p>';
    return;
  }

  const newestFirstLog = [...log].reverse();

  els.story.innerHTML = newestFirstLog
    .map(
      (entry) => `
        <article class="turn">
          <div class="turn-header">第 ${escapeHtml(entry.turn || "")} 轮</div>
          <p class="player-action"><strong>玩家：</strong>${escapeHtml(entry.player_input || "")}</p>
          ${renderDialogue(entry.dialogue || {})}
        </article>
      `
    )
    .join("");
}

function escapeHtml(text) {
  return String(text)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function validateConfig(config) {
  if (!config.base_url || !config.api_key || !config.model) {
    return "请先填写 Base URL、API Key 和 Model Name。";
  }
  return "";
}

async function postJson(url, body) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return response.json();
}

async function testModel() {
  const config = readConfig();
  const error = validateConfig(config);
  if (error) {
    setStatus(els.configStatus, error, "error");
    return;
  }

  els.testModelBtn.disabled = true;
  setStatus(els.configStatus, "测试中...");
  try {
    const result = await postJson("/api/test_model", config);
    if (result.success) {
      setStatus(els.configStatus, `成功：${result.message}`, "ok");
    } else {
      setStatus(els.configStatus, result.error || "测试失败。", "error");
    }
  } catch (err) {
    setStatus(els.configStatus, err.message, "error");
  } finally {
    els.testModelBtn.disabled = false;
  }
}

async function sendTurn() {
  const config = readConfig();
  const error = validateConfig(config);
  const playerInput = els.playerInput.value.trim();
  if (error) {
    setStatus(els.turnStatus, error, "error");
    return;
  }
  if (!playerInput) {
    setStatus(els.turnStatus, "请输入玩家行动。", "error");
    return;
  }

  els.sendBtn.disabled = true;
  setStatus(els.turnStatus, "生成中...");
  try {
    const result = await postJson("/api/turn", {
      ...config,
      player_input: playerInput,
      state,
    });

    if (result.ok) {
      lastAgentOutput = result.agent_output;
      state = result.new_state;
      saveState();
      renderStory();
      renderAgentOutput(lastAgentOutput);
      renderState();
      els.playerInput.value = "";
      setStatus(els.turnStatus, `第 ${state.turn} 轮已生成。`, "ok");
    } else {
      setStatus(els.turnStatus, result.error || "生成失败。", "error");
      renderAgentOutput({ error: result.error, raw_output: result.raw_output });
    }
  } catch (err) {
    setStatus(els.turnStatus, err.message, "error");
  } finally {
    els.sendBtn.disabled = false;
  }
}

async function suggestInput() {
  const config = readConfig();
  const error = validateConfig(config);
  if (error) {
    setStatus(els.turnStatus, error, "error");
    return;
  }

  els.suggestInputBtn.disabled = true;
  setStatus(els.turnStatus, "正在生成推进输入...");
  try {
    const result = await postJson("/api/suggest_input", {
      ...config,
      state,
    });
    if (result.ok) {
      els.playerInput.value = result.player_input || "";
      els.playerInput.focus();
      setStatus(els.turnStatus, "已生成一条可编辑的推进输入。", "ok");
    } else {
      setStatus(els.turnStatus, result.error || "推进输入生成失败。", "error");
    }
  } catch (err) {
    setStatus(els.turnStatus, err.message, "error");
  } finally {
    els.suggestInputBtn.disabled = false;
  }
}

async function resetSession() {
  try {
    state = await postJson("/api/reset", {});
  } catch {
    state = clone(INITIAL_STATE);
  }
  lastAgentOutput = null;
  saveState();
  renderStory();
  renderAgentOutput(null);
  renderState();
  setStatus(els.turnStatus, "会话已重置。", "ok");
}

function exportDebugJson() {
  const config = readConfig();
  const debug = {
    api_config: {
      base_url: config.base_url,
      model: config.model,
      disable_thinking: config.disable_thinking,
    },
    state,
    conversation_log: state.conversation_log || [],
    last_agent_output: lastAgentOutput,
  };
  const blob = new Blob([JSON.stringify(debug, null, 2)], {
    type: "application/json",
  });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = "debug.json";
  link.click();
  URL.revokeObjectURL(link.href);
}

function init() {
  const config = loadConfig();
  els.baseUrl.value = config.base_url;
  els.apiKey.value = config.api_key;
  els.modelName.value = config.model;
  els.disableThinking.checked = config.disable_thinking;

  els.saveConfigBtn.addEventListener("click", saveConfig);
  els.testModelBtn.addEventListener("click", testModel);
  els.suggestInputBtn.addEventListener("click", suggestInput);
  els.sendBtn.addEventListener("click", sendTurn);
  els.resetBtn.addEventListener("click", resetSession);
  els.exportBtn.addEventListener("click", exportDebugJson);

  renderStory();
  renderAgentOutput(null);
  renderState();
}

init();
