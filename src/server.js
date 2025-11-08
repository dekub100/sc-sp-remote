const express = require("express");
const http = require("http");
const path = require("path");
const config = require("./config");
const { setupWebSocket } = require("./websocket");
const { startProgressBroadcasting } = require("./utils");

function startServer() {
  const app = express();
  const server = http.createServer(app);

  setupWebSocket(server);

  app.use(express.static(path.join(__dirname, "..", "website")));

  if (config.enableOBS) {
    app.use("/obs", express.static(path.join(__dirname, "..", "obs-widget")));
    app.get("/obs", (req, res) => {
      res.sendFile(path.join(__dirname, "..", "obs-widget", "obs-widget.html"));
    });
  }

  app.get("/", (req, res) => {
    res.sendFile(path.join(__dirname, "..", "website", "index.html"));
  });

  app.get("/api/config", (req, res) => {
    res.json({ port: config.port });
  });

  const configServer = http.createServer((req, res) => {
    if (req.url === "/api/config") {
      res.writeHead(200, {
        "Content-Type": "application/json",
        "Access-Control-Allow-Origin": config.allowedOrigins.join(","),
      });
      res.end(
        JSON.stringify({
          port: config.port,
          configPort: config.configPort,
          allowedOrigins: config.allowedOrigins,
          defaultVolume: config.defaultVolume,
          enableOBS: config.enableOBS,
        })
      );
    } else {
      res.writeHead(404, {
        "Access-Control-Allow-Origin": config.allowedOrigins.join(","),
      });
      res.end();
    }
  });

  configServer.listen(config.configPort, "127.0.0.1", () => {
    console.log(
      `Config server running at http://127.0.0.1:${config.configPort}/api/config`
    );
  });

  server.listen(config.port, "127.0.0.1", () => {
    console.log(`Server is running at http://127.0.0.1:${config.port}`);
    console.log(`WebSocket server is listening on 127.0.0.1:${config.port}`);
  });

  startProgressBroadcasting();
}

module.exports = { startServer };
