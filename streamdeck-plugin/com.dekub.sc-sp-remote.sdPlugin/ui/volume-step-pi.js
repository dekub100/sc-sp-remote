function applySettings(settings) {
  const sourceInput = document.getElementById("sourceInput");
  if (sourceInput && settings.source !== undefined) {
    sourceInput.value = settings.source;
  }
  const stepInput = document.getElementById("stepInput");
  if (stepInput && settings.step !== undefined) {
    stepInput.value = Math.round(settings.step * 100);
  }
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
});
