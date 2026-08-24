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

function applySettings(settings) {
  const volumeInput = document.getElementById("volumeInput");
  if (volumeInput && settings.volume !== undefined) {
    volumeInput.value = (settings.volume * 100).toFixed(0);
  }
  const sourceInput = document.getElementById("sourceInput");
  if (sourceInput && settings.source !== undefined) {
    sourceInput.value = settings.source;
  }
}

document.addEventListener("DOMContentLoaded", function () {
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
    sourceInput.addEventListener("change", function () {
      websocket.send(JSON.stringify({
        event: "setSettings",
        context: uuid,
        payload: getSettingsPayload(),
      }));
    });
  }
});
