// Shared property-inspector boilerplate.
// Pages optionally define `applySettings(settings)` to receive their action's
// settings on load; everything else (websocket, registration, port input,
// status dot) is handled here.
let websocket;
let uuid;

function connectElgatoStreamDeckSocket(inPort, inUUID, inRegisterEvent) {
  uuid = inUUID;
  websocket = new WebSocket("ws://127.0.0.1:" + inPort);

  websocket.onopen = function () {
    const send = (payload) => websocket.send(JSON.stringify(payload));
    send({ event: inRegisterEvent, uuid: inUUID });
    if (typeof applySettings === "function") send({ event: "getSettings", context: uuid });
    send({ event: "getGlobalSettings", context: uuid });
  };

  websocket.onmessage = function (event) {
    const { payload, event: type } = JSON.parse(event.data);
    if (type === "didReceiveSettings" && typeof applySettings === "function") {
      applySettings(payload.settings);
    }
    if (type === "didReceiveGlobalSettings") {
      applyGlobalSettings(payload.settings);
    }
  };

  websocket.onclose = function () {
    console.log("PI: WebSocket closed.");
  };

  websocket.onerror = function (error) {
    console.error("PI: WebSocket error:", error);
  };
}

function applyGlobalSettings(settings) {
  const portInput = document.getElementById("portInput");
  if (portInput && settings.port !== undefined) {
    portInput.value = settings.port;
  }
  const dot = document.getElementById("statusDot");
  const text = document.getElementById("statusText");
  if (!dot || !text) return;
  dot.style.background = settings.connected === true ? "#4caf50" : settings.connected === false ? "#f44336" : "#888";
  text.textContent = settings.connected === true ? "Connected" : settings.connected === false ? "Disconnected" : "Checking...";
}

function savePortSetting() {
  let newPort = parseInt(document.getElementById("portInput").value);
  if (isNaN(newPort) || newPort < 1) newPort = 8888;
  if (newPort > 65535) newPort = 65535;
  document.getElementById("portInput").value = newPort;
  websocket.send(JSON.stringify({
    event: "setGlobalSettings",
    context: uuid,
    payload: { port: newPort },
  }));
}

document.addEventListener("DOMContentLoaded", function () {
  const portInput = document.getElementById("portInput");
  if (portInput) {
    portInput.addEventListener("change", savePortSetting);
  }
});
