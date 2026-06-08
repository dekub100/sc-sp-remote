let websocket;
let uuid;

function connectElgatoStreamDeckSocket(inPort, inUUID, inRegisterEvent, inInfo) {
  uuid = inUUID;
  websocket = new WebSocket("ws://127.0.0.1:" + inPort);

  websocket.onopen = function () {
    console.log("PI: WebSocket opened.");
    websocket.send(JSON.stringify({
      event: inRegisterEvent,
      uuid: inUUID,
    }));
    websocket.send(JSON.stringify({
      event: "getSettings",
      context: uuid,
    }));
    websocket.send(JSON.stringify({
      event: "getGlobalSettings",
      context: uuid,
    }));
  };

  websocket.onmessage = function (event) {
    const { payload, event: type } = JSON.parse(event.data);
    console.log("PI: Received message:", type, payload);
    if (type === "didReceiveSettings") {
      const { settings } = payload;
      const volumeInput = document.getElementById("volumeInput");
      if (volumeInput && settings.volume !== undefined) {
        volumeInput.value = (settings.volume * 100).toFixed(0);
      }
      const sourceInput = document.getElementById("sourceInput");
      if (sourceInput && settings.source !== undefined) {
        sourceInput.value = settings.source;
      }
    }
    if (type === "didReceiveGlobalSettings") {
      const { settings } = payload;
      const portInput = document.getElementById("portInput");
      if (portInput && settings.port !== undefined) {
        portInput.value = settings.port;
      }
      const dot = document.getElementById("statusDot");
      const text = document.getElementById("statusText");
      if (dot && text) {
        if (settings.connected === true) {
          dot.style.background = "#4caf50";
          text.textContent = "Connected";
        } else if (settings.connected === false) {
          dot.style.background = "#f44336";
          text.textContent = "Disconnected";
        } else {
          dot.style.background = "#888";
          text.textContent = "Checking...";
        }
      }
    }
  };

  websocket.onclose = function () {
    console.log("PI: WebSocket closed.");
  };

  websocket.onerror = function (error) {
    console.error("PI: WebSocket error:", error);
  };
}

document.addEventListener("DOMContentLoaded", function () {
  function getSettingsPayload() {
    const volumeInput = document.getElementById("volumeInput");
    const sourceInput = document.getElementById("sourceInput");
    const payload = {};
    if (volumeInput) {
      let v = parseInt(volumeInput.value);
      if (isNaN(v)) v = 0;
      payload.volume = Math.max(0, Math.min(100, v)) / 100;
    }
    if (sourceInput) payload.source = sourceInput.value;
    return payload;
  }

  const volumeInput = document.getElementById("volumeInput");
  if (volumeInput) {
    volumeInput.addEventListener("change", function (e) {
      let newVolume = parseInt(e.target.value);
      if (isNaN(newVolume)) newVolume = 0;
      newVolume = Math.max(0, Math.min(100, newVolume));
      e.target.value = newVolume;
      websocket.send(JSON.stringify({
        event: "setSettings",
        context: uuid,
        payload: getSettingsPayload(),
      }));
    });
  }

  const sourceInput = document.getElementById("sourceInput");
  if (sourceInput) {
    sourceInput.addEventListener("change", function (e) {
      websocket.send(JSON.stringify({
        event: "setSettings",
        context: uuid,
        payload: getSettingsPayload(),
      }));
    });
  }

  const portInput = document.getElementById("portInput");
  if (portInput) {
    portInput.addEventListener("change", function (e) {
      let newPort = parseInt(e.target.value);
      if (isNaN(newPort) || newPort < 1) newPort = 8888;
      if (newPort > 65535) newPort = 65535;
      e.target.value = newPort;
      websocket.send(JSON.stringify({
        event: "setGlobalSettings",
        context: uuid,
        payload: { port: newPort },
      }));
    });
  }
});
