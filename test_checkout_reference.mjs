import { spawn } from "node:child_process";

const url = "file:///home/ubuntu/ptr-connect/checkout-reference.html";
const port = 9227;
const profile = "/tmp/ptr-checkout-chrome-profile";
const chrome = spawn("chromium", [
  "--headless", "--no-sandbox", "--disable-gpu", "--remote-allow-origins=*",
  `--remote-debugging-port=${port}`, `--user-data-dir=${profile}`, "about:blank"
], { stdio: "ignore" });

const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
async function waitForTargets() {
  for (let attempt = 0; attempt < 30; attempt += 1) {
    try {
      const response = await fetch(`http://127.0.0.1:${port}/json/new?${encodeURIComponent(url)}`, { method: "PUT" });
      if (response.ok) return response.json();
    } catch {}
    await delay(200);
  }
  throw new Error("Chrome DevTools endpoint did not become available.");
}

let sequence = 0;
const target = await waitForTargets();
const socket = new WebSocket(target.webSocketDebuggerUrl);
const pending = new Map();
await new Promise((resolve, reject) => {
  socket.addEventListener("open", resolve, { once: true });
  socket.addEventListener("error", reject, { once: true });
});
socket.addEventListener("message", event => {
  const message = JSON.parse(event.data);
  if (message.id && pending.has(message.id)) {
    const { resolve, reject } = pending.get(message.id);
    pending.delete(message.id);
    message.error ? reject(new Error(message.error.message)) : resolve(message.result);
  }
});
const send = (method, params = {}) => new Promise((resolve, reject) => {
  const id = ++sequence;
  pending.set(id, { resolve, reject });
  socket.send(JSON.stringify({ id, method, params }));
});
const evaluate = async expression => {
  const result = await send("Runtime.evaluate", { expression, returnByValue: true, awaitPromise: true });
  if (result.exceptionDetails) throw new Error(result.exceptionDetails.text || "Page evaluation failed.");
  return result.result.value;
};

try {
  await delay(800);
  const eventCheck = await evaluate(`new Promise(resolve => {
    window.addEventListener("ptr:checkout-method", event => resolve({ id: event.detail.method.id, invoice: event.detail.invoice.reference }), { once: true });
    document.querySelector('[data-method="card"]').click();
  })`);
  const cardState = await evaluate(`({
    pressed: document.querySelector('[data-method="card"]').getAttribute("aria-pressed"),
    summary: document.getElementById("summaryMethod").textContent,
    button: document.getElementById("continueLabel").textContent
  })`);
  const handoffCheck = await evaluate(`new Promise(resolve => {
    window.addEventListener("ptr:checkout-continue", event => resolve({ id: event.detail.method.id, balance: event.detail.invoice.balance }), { once: true });
    document.getElementById("continueButton").click();
  })`);
  const khqrEventCheck = await evaluate(`new Promise(resolve => {
    window.addEventListener("ptr:checkout-method", event => resolve({ id: event.detail.method.id, invoice: event.detail.invoice.reference }), { once: true });
    document.querySelector('[data-method="aba-khqr"]').click();
  })`);
  const khqrState = await evaluate(`({
    pressed: document.querySelector('[data-method="aba-khqr"]').getAttribute("aria-pressed"),
    summary: document.getElementById("summaryMethod").textContent,
    button: document.getElementById("continueLabel").textContent
  })`);
  const khqrHandoffCheck = await evaluate(`new Promise(resolve => {
    window.addEventListener("ptr:checkout-continue", event => resolve({ id: event.detail.method.id, balance: event.detail.invoice.balance }), { once: true });
    document.getElementById("continueButton").click();
  })`);
  const status = await evaluate(`document.getElementById("referenceStatus").textContent`);

  const widths = [
    { name: "iphone", width: 390, height: 844 },
    { name: "android", width: 412, height: 915 },
    { name: "ipad", width: 768, height: 1024 },
    { name: "desktop", width: 1440, height: 1000 }
  ];
  const responsive = [];
  for (const viewport of widths) {
    await send("Emulation.setDeviceMetricsOverride", { width: viewport.width, height: viewport.height, deviceScaleFactor: 1, mobile: viewport.width < 620 });
    await delay(120);
    responsive.push(await evaluate(`(() => ({
      name: "${viewport.name}",
      viewport: window.innerWidth,
      pageFits: document.documentElement.scrollWidth <= window.innerWidth + 1,
      methodsFit: [...document.querySelectorAll(".paymentMethod")].every(node => node.scrollWidth <= node.clientWidth + 1),
      selectedText: document.getElementById("summaryMethod").textContent,
      selectedVisible: document.getElementById("summaryMethod").getBoundingClientRect().width > 0
    }))()`));
  }
  const results = { eventCheck, cardState, handoffCheck, khqrEventCheck, khqrState, khqrHandoffCheck, status, responsive };
  console.log(JSON.stringify(results, null, 2));
  const failed = !eventCheck || cardState.pressed !== "true" || cardState.summary !== "Credit / Debit Card" || handoffCheck.id !== "card" || !khqrEventCheck || khqrState.pressed !== "true" || khqrState.summary !== "ABA KHQR" || khqrHandoffCheck.id !== "aba-khqr" || !status.includes("no payment was submitted") || responsive.some(view => !view.pageFits || !view.methodsFit || !view.selectedVisible);
  if (failed) process.exitCode = 1;
} finally {
  socket.close();
  chrome.kill("SIGTERM");
}
