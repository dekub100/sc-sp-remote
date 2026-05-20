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
        console.log("PI: Settings loaded into UI:", settings.volume);
      }
    }
    if (type === "didReceiveGlobalSettings") {
      const { settings } = payload;
      const portInput = document.getElementById("portInput");
      if (portInput && settings.port !== undefined) {
        portInput.value = settings.port;
        console.log("PI: Global port loaded:", settings.port);
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
  const volumeInput = document.getElementById("volumeInput");
  if (volumeInput) {
    volumeInput.addEventListener("change", function (e) {
      let newVolume = parseInt(e.target.value);
      if (isNaN(newVolume)) newVolume = 0;
      newVolume = Math.max(0, Math.min(100, newVolume));
      e.target.value = newVolume;

      const volumeToSend = newVolume / 100;
      websocket.send(JSON.stringify({
        event: "setSettings",
        context: uuid,
        payload: { volume: volumeToSend },
      }));
      console.log("PI: Volume sent:", volumeToSend);
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
      console.log("PI: Global port set to:", newPort);
    });
  }
});
