#!/usr/bin/env node
/** Inicia o backend na porta 8001 (Windows, macOS, Linux). */
const { spawn } = require("child_process");
const path = require("path");

const root = path.join(__dirname, "..");
const port = process.env.PORT || "8001";
const env = {
  ...process.env,
  PORT: port,
  ENVIRONMENT: process.env.ENVIRONMENT || "development",
};

const python = process.platform === "win32" ? "python" : "python3";
console.log(`[backend] Thora API em http://localhost:${port}`);

const child = spawn(python, ["main.py"], { cwd: root, env, stdio: "inherit" });
child.on("exit", (code) => process.exit(code ?? 0));
