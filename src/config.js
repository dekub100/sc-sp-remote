const path = require("path");
const fs = require("fs");

const configPath = path.join(__dirname, "..", "config.json");
let config = {
  port: 8888,
  configPort: 54321,
  allowedOrigins: ["*"],
  defaultVolume: 0.5,
  enableOBS: true,
};

try {
  if (fs.existsSync(configPath)) {
    config = { ...config, ...JSON.parse(fs.readFileSync(configPath, "utf8")) };
  }
} catch (err) {
  console.error("Failed to read config.json, using defaults.", err);
}

module.exports = config;
