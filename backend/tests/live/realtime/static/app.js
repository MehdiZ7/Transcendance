"use strict";

// Close codes sent by transport.py, plus 1006 which the browser reports
// when the socket died without a close frame.
const CLOSE_POLICY = {
  1000: { label: "normal", reconnect: false },
  1001: { label: "going away", reconnect: true },
  1006: { label: "abnormal, no close frame", reconnect: true },
  1008: { label: "policy violation", reconnect: false },
  1009: { label: "frame too big", reconnect: false },
  1011: { label: "internal error", reconnect: true },
  1013: { label: "try again later (gap)", reconnect: true },
  4000: { label: "replaced by another connection", reconnect: false },
  4001: { label: "simulated drop (this page)", reconnect: true },
};

const MAX_LOG = 500;
const BACKOFF_MS = [250, 500, 1000, 2000, 4000, 8000];

let heartbeatMs = 25_000;
let clientCount = 0;

const $ = (selector, root = document) => root.querySelector(selector);

function wsUrl(user) {
  const scheme = location.protocol === "https:" ? "wss" : "ws";
  return `${scheme}://${location.host}/ws?user=${encodeURIComponent(user)}`;
}

function topicKey(kind, id) {
  return id ? `${kind}:${id}` : kind;
}

function clock() {
  return new Date().toLocaleTimeString([], { hour12: false }) +
    "." + String(Date.now() % 1000).padStart(3, "0");
}

// ── one client = one browser tab ────────────────────────────────

class Client {
  constructor({ principal, token = null, lastSeq = 0, subs = [] }) {
    this.n = ++clientCount;
    this.principal = principal;
    this.token = token;
    this.lastSeq = lastSeq;
    this.subs = new Map(subs); // key -> {topic_kind, topic_id}
    this.ws = null;
    this.state = "idle";
    this.ref = 0;
    this.retries = 0;
    this.retryTimer = null;
    this.heartbeat = null;
    this.pings = new Map(); // send time of pending pings, oldest first
    this.stayDown = false;

    this.el = $("#client-template").content.firstElementChild.cloneNode(true);
    $(".principal", this.el).textContent = `${principal} #${this.n}`;
    this.bind();
    this.render();
  }

  // DOM

  bind() {
    const el = this.el;
    const actions = {
      connect: () => this.connect(),
      disconnect: () => this.disconnect(),
      drop: () => this.drop(),
      clone: () => bench.addClient({
        principal: this.principal,
        token: this.token,
        lastSeq: this.lastSeq,
        subs: [...this.subs],
      }).connect(),
      forget: () => { this.token = null; this.lastSeq = 0; this.note("token forgotten"); this.render(); },
      ping: () => this.ping(),
      typing: () => this.message("typing.start", {}),
      flood: () => { for (let i = 0; i < 30; i++) this.ping(); },
      clear: () => { $(".log", el).replaceChildren(); },
    };
    for (const button of el.querySelectorAll("[data-action]")) {
      button.addEventListener("click", () => actions[button.dataset.action]());
    }
    $(".remove", el).addEventListener("click", () => this.remove());

    $("form.subscribe", el).addEventListener("submit", (e) => {
      e.preventDefault();
      const { kind, id } = this.topicInputs();
      this.subscribe(kind, id);
    });
    $("form.chat", el).addEventListener("submit", (e) => {
      e.preventDefault();
      const input = e.target.elements.text;
      if (!input.value.trim()) return;
      this.message("message.create", { text: input.value });
      input.value = "";
    });
    $(".raw form", el).addEventListener("submit", (e) => {
      e.preventDefault();
      this.sendRaw(e.target.elements.raw.value);
    });
    $("[name=heartbeat]", el).addEventListener("change", () => this.armHeartbeat());
  }

  option(name) {
    return $(`[name=${name}]`, this.el).checked;
  }

  topicInputs() {
    const form = $("form.subscribe", this.el).elements;
    return { kind: form.kind.value.trim(), id: form.id.value.trim() || null };
  }

  render() {
    const open = this.state === "open";
    const badge = $(".state", this.el);
    badge.textContent = this.state;
    badge.className = `badge state ${this.state}`;
    $(".meta", this.el).textContent =
      `${this.token ? this.token.slice(0, 8) + "…" : "no token"} · seq ${this.lastSeq}`;

    const live = this.state === "open" || this.state === "connecting";
    const button = (action) => $(`[data-action=${action}]`, this.el);
    button("connect").disabled = live;
    button("disconnect").disabled = !live && !this.retryTimer;
    button("drop").disabled = !live;
    button("clone").disabled = !this.token;
    button("forget").disabled = !this.token || live;
    for (const b of this.el.querySelectorAll(
      "form button, [data-action=ping], [data-action=typing], [data-action=flood]"
    )) {
      b.disabled = !open;
    }

    const chips = $(".subs", this.el);
    chips.replaceChildren(...[...this.subs.keys()].map((key) => {
      const li = document.createElement("li");
      li.textContent = key;
      const x = document.createElement("button");
      x.type = "button";
      x.textContent = "×";
      x.title = "Unsubscribe";
      x.disabled = !open;
      x.addEventListener("click", () => this.unsubscribe(key));
      li.append(x);
      return li;
    }));
  }

  log(kind, text, dir = "") {
    const list = $(".log", this.el);
    const stick = list.scrollTop + list.clientHeight >= list.scrollHeight - 4;
    const li = document.createElement("li");
    li.className = kind;
    const time = document.createElement("time");
    time.textContent = clock();
    const arrow = document.createElement("span");
    arrow.className = "dir";
    arrow.textContent = dir;
    const code = document.createElement("code");
    code.textContent = text;
    li.append(time, arrow, code);
    list.append(li);
    while (list.children.length > MAX_LOG) list.firstElementChild.remove();
    if (stick) list.scrollTop = list.scrollHeight;
  }

  note(text) { this.log("note", `· ${text}`); }
  warn(text) { this.log("warn", `! ${text}`); }

  // Socket lifecycle

  connect() {
    clearTimeout(this.retryTimer);
    this.retryTimer = null;
    this.stayDown = false;
    this.state = "connecting";
    this.render();

    const ws = new WebSocket(wsUrl(this.principal));
    this.ws = ws;
    ws.addEventListener("open", () => this.onOpen(ws));
    ws.addEventListener("message", (e) => this.onFrame(ws, e.data));
    ws.addEventListener("close", (e) => this.onClose(ws, e));
  }

  onOpen(ws) {
    if (ws !== this.ws) return;
    // The server waits for a first frame: resume if we can, ping otherwise
    if (this.token && this.option("resume")) {
      this.send({ type: "resume", session: this.token, last_seq: this.lastSeq });
    } else {
      this.ping();
    }
  }

  onFrame(ws, raw) {
    if (ws !== this.ws) return;
    let frame;
    try {
      frame = JSON.parse(raw);
    } catch {
      this.log("bad", raw, "←");
      return;
    }
    this.log(frame.type === "error" ? "in error" : "in", raw, "←");

    switch (frame.type) {
      case "session": return this.onSession(frame);
      case "error": return this.onError(frame);
      case "pong": return this.onPong();
      default: return this.onEvent(frame);
    }
  }

  onSession(frame) {
    this.token = frame.session;
    this.state = "open";
    this.retries = 0;
    if (frame.resumed) {
      if (frame.from_seq !== this.lastSeq + 1) {
        this.warn(`resumed from ${frame.from_seq}, expected ${this.lastSeq + 1}`);
      }
      this.note(`resumed, replay from seq ${frame.from_seq}`);
    } else {
      this.lastSeq = 0;
      if (this.subs.size) {
        this.note(`fresh stream (${frame.reason}): resubscribing ${this.subs.size} topic(s)`);
        for (const sub of this.subs.values()) this.send({ type: "subscribe", ...sub });
      } else {
        this.note(`fresh stream (${frame.reason})`);
      }
    }
    this.armHeartbeat();
    this.render();
  }

  onError(frame) {
    // A refused subscribe has no ref: forget the optimistic subscription
    if (!frame.ref && ["forbidden", "unknown_topic"].includes(frame.code)) {
      const key = topicKey(frame.topic_kind, frame.topic_id);
      if (this.subs.delete(key)) this.render();
    }
  }

  onPong() {
    const [first] = this.pings.keys();
    if (first === undefined) return;
    this.note(`rtt ${Math.round(performance.now() - this.pings.get(first))} ms`);
    this.pings.delete(first);
  }

  onEvent(frame) {
    if (frame.seq !== this.lastSeq + 1) {
      this.warn(`seq ${frame.seq} after ${this.lastSeq}: hole in the stream`);
    }
    this.lastSeq = frame.seq;
    this.render();
  }

  onClose(ws, event) {
    if (ws !== this.ws) return;
    this.ws = null;
    clearInterval(this.heartbeat);
    this.pings.clear();
    const policy = CLOSE_POLICY[event.code] ?? { label: "unknown", reconnect: true };
    const reason = event.reason ? ` "${event.reason}"` : "";
    this.log(event.code === 1000 ? "note" : "warn", `closed ${event.code}${reason}: ${policy.label}`, "×");

    this.state = event.code === 4000 ? "replaced" : "closed";
    if (!this.stayDown && policy.reconnect && this.option("auto")) {
      const delay = BACKOFF_MS[Math.min(this.retries++, BACKOFF_MS.length - 1)];
      this.note(`reconnecting in ${delay} ms`);
      this.retryTimer = setTimeout(() => this.connect(), delay);
    }
    this.render();
  }

  disconnect() {
    this.stayDown = true;
    clearTimeout(this.retryTimer);
    this.retryTimer = null;
    if (this.ws) {
      this.ws.close(1000, "bye");
    } else {
      this.render();
    }
  }

  drop() {
    // A browser cannot make a socket half-open; closing it and reconnecting
    // with resume is what a real network loss looks like to the server.
    this.note("dropping the socket");
    this.ws?.close(4001, "simulated drop");
  }

  remove() {
    this.disconnect();
    this.el.remove();
  }

  armHeartbeat() {
    clearInterval(this.heartbeat);
    if (this.option("heartbeat") && this.state === "open") {
      this.heartbeat = setInterval(() => this.ping(), heartbeatMs);
    }
  }

  // Frames

  send(frame) {
    this.sendRaw(JSON.stringify(frame));
  }

  sendRaw(raw) {
    if (this.ws?.readyState !== WebSocket.OPEN) {
      this.warn("socket not open");
      return;
    }
    this.ws.send(raw);
    this.log("out", raw, "→");
  }

  ping() {
    this.pings.set(Symbol(), performance.now());
    this.send({ type: "ping" });
  }

  subscribe(kind, id) {
    if (!kind) return;
    const sub = { topic_kind: kind, ...(id ? { topic_id: id } : {}) };
    this.subs.set(topicKey(kind, id), sub);
    this.send({ type: "subscribe", ...sub });
    this.render();
  }

  unsubscribe(key) {
    const sub = this.subs.get(key);
    if (!sub) return;
    this.subs.delete(key);
    this.send({ type: "unsubscribe", ...sub });
    this.render();
  }

  message(type, payload) {
    const { kind, id } = this.topicInputs();
    this.send({
      type,
      topic_kind: kind,
      ...(id ? { topic_id: id } : {}),
      ref: `c${this.n}-${++this.ref}`,
      payload,
    });
  }
}

// ── server side ─────────────────────────────────────────────────

const bench = {
  addClient(options) {
    const client = new Client(options);
    $("#clients").append(client.el);
    return client;
  },
};

async function post(url, body) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await response.json();
  if (!response.ok) throw new Error(JSON.stringify(data.detail ?? data));
  return data;
}

function formTopic(form) {
  return {
    topic_kind: form.topic_kind.value.trim(),
    topic_id: form.topic_id.value.trim() || null,
  };
}

$("#publish-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const form = e.target.elements;
  try {
    const payload = JSON.parse(form.payload.value || "{}");
    const { delivered } = await post("/api/publish", { type: form.type.value, ...formTopic(form), payload });
    form.result.value = `delivered to ${delivered} session(s)`;
  } catch (error) {
    form.result.value = `error: ${error.message}`;
  }
});

$("#burst-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const form = e.target.elements;
  try {
    const { delivered } = await post("/api/burst", { ...formTopic(form), count: Number(form.count.value) });
    form.result.value = `${delivered} deliveries`;
  } catch (error) {
    form.result.value = `error: ${error.message}`;
  }
});

$("#add-client").addEventListener("submit", (e) => {
  e.preventDefault();
  bench.addClient({ principal: e.target.elements.principal.value.trim() });
});

function cell(text, className = "") {
  const td = document.createElement("td");
  td.textContent = text;
  if (className) td.className = className;
  return td;
}

function renderStats({ config, sessions, topics }) {
  heartbeatMs = config.heartbeat * 1000;
  $("#server-config").textContent =
    `queue ${config.queue_limit} · replay ${config.replay_limit} · ttl ${config.ttl}s · ` +
    `idle ${config.idle_timeout}s · rate ${config.rate_limit}`;
  $("#session-count").textContent = `(${sessions.length})`;

  $("#sessions tbody").replaceChildren(...sessions.map((s) => {
    const tr = document.createElement("tr");
    tr.className = [s.state, s.gapped ? "gapped" : ""].join(" ");
    tr.append(
      cell(s.token.slice(0, 8) + "…", "mono"),
      cell(s.principal),
      cell(s.gapped ? `${s.state}, gap` : s.state),
      cell(s.epoch),
      cell(s.seq),
      cell(s.pending),
      cell(`${s.idle}s`),
      cell(s.topics.join(" "), "topics"),
    );
    return tr;
  }));

  $("#topics").replaceChildren(...Object.entries(topics).map(([topic, n]) => {
    const li = document.createElement("li");
    li.className = "plain";
    li.textContent = `${topic} ×${n}`;
    return li;
  }));
  if (!Object.keys(topics).length) {
    const li = document.createElement("li");
    li.className = "plain";
    li.textContent = "no topic";
    $("#topics").append(li);
  }
}

async function pollStats() {
  const status = $("#server-status");
  try {
    const response = await fetch("/api/stats");
    renderStats(await response.json());
    status.textContent = "server up";
    status.className = "badge ok";
  } catch {
    status.textContent = "server down";
    status.className = "badge down";
  }
  setTimeout(pollStats, 1000);
}

bench.addClient({ principal: "alice" });
bench.addClient({ principal: "bob" });
pollStats();
