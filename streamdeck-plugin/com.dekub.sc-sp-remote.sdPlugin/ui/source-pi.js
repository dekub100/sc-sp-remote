function applySettings(settings) {
  const sourceInput = document.getElementById("sourceInput");
  if (sourceInput && settings.source !== undefined) {
    sourceInput.value = settings.source;
  }
}

document.addEventListener("DOMContentLoaded", function () {
  const sourceInput = document.getElementById("sourceInput");
  if (sourceInput) {
    sourceInput.addEventListener("change", function (e) {
      websocket.send(JSON.stringify({
        event: "setSettings",
        context: uuid,
        payload: { source: e.target.value },
      }));
    });
  }
});
