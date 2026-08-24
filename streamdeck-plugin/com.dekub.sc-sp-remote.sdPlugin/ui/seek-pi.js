function applySettings(settings) {
  const sourceInput = document.getElementById("sourceInput");
  if (sourceInput && settings.source !== undefined) {
    sourceInput.value = settings.source;
  }
  const secondsInput = document.getElementById("secondsInput");
  if (secondsInput && settings.seconds !== undefined) {
    secondsInput.value = settings.seconds;
  }
}

document.addEventListener("DOMContentLoaded", function () {
  const sourceInput = document.getElementById("sourceInput");
  if (sourceInput) {
    sourceInput.addEventListener("change", function (e) {
      websocket.send(JSON.stringify({
        event: "setSettings",
        context: uuid,
        payload: { source: e.target.value, seconds: parseInt(document.getElementById("secondsInput").value) || 10 },
      }));
    });
  }

  const secondsInput = document.getElementById("secondsInput");
  if (secondsInput) {
    secondsInput.addEventListener("change", function (e) {
      let val = parseInt(e.target.value);
      if (isNaN(val) || val < 1) val = 10;
      if (val > 300) val = 300;
      e.target.value = val;
      websocket.send(JSON.stringify({
        event: "setSettings",
        context: uuid,
        payload: { seconds: val, source: document.getElementById("sourceInput").value },
      }));
    });
  }
});
