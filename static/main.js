const INITIAL_STATE = {
  turn: 0,
  world_state: {
    scene_goal: "维持协作并推进当前项目",
    pressure: "中等",
    recent_public_events: [],
  },
  characters: {
    A: {
      emotions: ["克制", "观察"],
      beliefs_about_player: [],
      intention: "观察玩家如何处理协作压力",
    },
    B: {
      emotions: ["好奇", "试探"],
      beliefs_about_player: [],
      intention: "用轻松方式接近玩家",
    },
    C: {
      emotions: ["安静", "警觉"],
      beliefs_about_player: [],
      intention: "先观察，再用行动提供帮助",
    },
  },
  open_threads: [],
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
    return saved || clone(INITIAL_STATE);
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

  els.story.innerHTML = log
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
  setStatus(els.turnStatus, "正在生成参考输入...");
  try {
    const result = await postJson("/api/suggest_input", {
      ...config,
      state,
    });
    if (result.ok) {
      els.playerInput.value = result.player_input || "";
      els.playerInput.focus();
      setStatus(els.turnStatus, "已生成一条可编辑的参考输入。", "ok");
    } else {
      setStatus(els.turnStatus, result.error || "参考输入生成失败。", "error");
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
