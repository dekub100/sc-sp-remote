let websocket;
let uuid;

function connectElgatoStreamDeckSocket(inPort, inUUID, inRegisterEvent, inInfo) {
  uuid = inUUID;
  websocket = new WebSocket("ws://127.0.0.1:" + inPort);

  websocket.onopen = function () {
    console.log("PI: WebSocket opened.");
    const json = {
      event: inRegisterEvent,
      uuid: inUUID,
    };
    websocket.send(JSON.stringify(json));
    // Request settings when PI opens
    websocket.send(JSON.stringify({
      event: "getSettings",
      context: uuid,
    }));
  };

  websocket.onmessage = function (event) {
    const { payload, event: type, context } = JSON.parse(event.data);
    console.log("PI: Received message:", type, payload);
    if (type === "didReceiveSettings") {
      const { settings } = payload;
      const volumeInput = document.getElementById("volumeInput");

      if (volumeInput && settings.volume !== undefined) {
        // Convert volume (0.0-1.0) to percentage (0-100) for the input field
        volumeInput.value = (settings.volume * 100).toFixed(0);
        console.log("PI: Settings loaded into UI:", settings.volume);
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
    volumeInput.addEventListener("change", function (e) { // Use 'change' event for number input
      let newVolume = parseInt(e.target.value);
      if (isNaN(newVolume)) newVolume = 0; // Handle non-numeric input
      newVolume = Math.max(0, Math.min(100, newVolume)); // Clamp between 0 and 100
      e.target.value = newVolume; // Update input field if clamped

      const volumeToSend = newVolume / 100; // Convert percentage back to 0.0-1.0
      const json = {
        event: "setSettings",
        context: uuid,
        payload: {
          volume: volumeToSend,
        },
      };
      websocket.send(JSON.stringify(json));
      console.log("PI: Settings sent to plugin:", volumeToSend);
    });
  }
});
