let websocket;
let uuid;

function connectElgatoStreamDeckSocket(inPort, inUUID, inRegisterEvent, inInfo) {
  uuid = inUUID;
  websocket = new WebSocket("ws://127.0.0.1:" + inPort);

  websocket.onopen = function () {
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
    if (type === "didReceiveSettings") {
      const { settings } = payload;
      const sourceInput = document.getElementById("sourceInput");
      if (sourceInput && settings.source !== undefined) {
        sourceInput.value = settings.source;
      }
      const stepInput = document.getElementById("stepInput");
      if (stepInput && settings.step !== undefined) {
        stepInput.value = Math.round(settings.step * 100);
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
  const sourceInput = document.getElementById("sourceInput");
  if (sourceInput) {
    sourceInput.addEventListener("change", function (e) {
      const step = (parseInt(document.getElementById("stepInput").value) || 5) / 100;
      websocket.send(JSON.stringify({
        event: "setSettings",
        context: uuid,
        payload: { source: e.target.value, step },
      }));
    });
  }

  const stepInput = document.getElementById("stepInput");
  if (stepInput) {
    stepInput.addEventListener("change", function (e) {
      let val = parseInt(e.target.value);
      if (isNaN(val) || val < 1) val = 5;
      if (val > 100) val = 100;
      e.target.value = val;
      const step = val / 100;
      websocket.send(JSON.stringify({
        event: "setSettings",
        context: uuid,
        payload: { step, source: document.getElementById("sourceInput").value },
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
