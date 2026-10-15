const { spawn, execSync } = require("child_process");
const dgram = require("dgram");
const fs = require("fs");
const os = require("os");
const path = require("path");

const APP = path.resolve(__dirname, "..");
const BACKEND = path.resolve(APP, "..", "backend");
const PYTHON = path.join(BACKEND, "venv", "Scripts", "python.exe");
const LOGS = path.join(os.tmpdir(), "finexa-demo-logs");
const children = [];

const say = (text) => console.log(`\n\x1b[36m>> ${text}\x1b[0m`);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function freePort(port) {
  const out = execSync("netstat -ano -p tcp").toString();
  const pids = new Set(
    out
      .split("\n")
      .filter((line) => line.includes(`:${port} `) && line.includes("LISTENING"))
      .map((line) => line.trim().split(/\s+/).pop())
  );
  for (const pid of pids) {
    try {
      execSync(`taskkill /PID ${pid} /T /F`, { stdio: "ignore" });
    } catch {} // already gone
  }
}

async function waitFor(url, seconds) {
  for (let i = 0; i < seconds; i++) {
    try {
      if ((await fetch(url, { signal: AbortSignal.timeout(5000) })).ok) return true;
    } catch {}
    await sleep(1000);
  }
  return false;
}

function lanAddress() {
  return new Promise((resolve) => {
    const socket = dgram.createSocket("udp4");
    socket.connect(80, "8.8.8.8", () => {
      const { address } = socket.address(); // no data is sent, this only asks Windows which network it would use
      socket.close();
      resolve(address);
    });
  });
}

function start(command, args, options) {
  const child = spawn(command, args, { windowsHide: true, ...options });
  children.push(child);
  return child;
}

function stopAll() {
  for (const child of children) {
    try {
      execSync(`taskkill /PID ${child.pid} /T /F`, { stdio: "ignore" }); // /T also stops its child processes
    } catch {}
  }
}

async function main() {
  fs.mkdirSync(LOGS, { recursive: true });
  say("Stopping anything left from an earlier run (ports 8000 and 8081)...");
  freePort(8000);
  freePort(8081);

  say("Starting the backend on port 8000...");
  const backendLog = fs.openSync(path.join(LOGS, "backend.log"), "w");
  start(PYTHON, ["-m", "uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000"], {
    cwd: BACKEND,
    stdio: ["ignore", backendLog, backendLog],
  });
  if (!(await waitFor("http://localhost:8000/demo", 30)))
    throw new Error(`Backend did not start. See ${path.join(LOGS, "backend.log")}`);
  say("Backend is running.");

  say("Starting the Cloudflare tunnel...");
  const cloudflared = require("cloudflared"); // npm package that ships the official cloudflared.exe
  if (!fs.existsSync(cloudflared.bin)) {
    say("Downloading cloudflared (only the first time)...");
    await cloudflared.install(cloudflared.bin);
  }
  const tunnelLog = fs.createWriteStream(path.join(LOGS, "tunnel.log"));
  const tunnel = start(cloudflared.bin, ["tunnel", "--url", "http://localhost:8000"], {});
  const url = await new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error("No tunnel address after 90 s. See tunnel.log")), 90000);
    const onData = (data) => {
      tunnelLog.write(data);
      const match = data.toString().match(/https:\/\/[a-z0-9-]+\.trycloudflare\.com/);
      if (match) {
        clearTimeout(timer);
        resolve(match[0]);
      }
    };
    tunnel.stdout.on("data", onData);
    tunnel.stderr.on("data", onData);
  });
  fs.writeFileSync(path.join(APP, ".env.local"), `EXPO_PUBLIC_API_URL=${url}\n`);
  say(`Tunnel address ${url} written to app/.env.local. Checking it works...`);
  say((await waitFor(`${url}/demo`, 60)) ? "Tunnel works." : "Tunnel does not answer yet; the app shows the offline demo until it does.");

  const ip = await lanAddress();
  say(`Laptop address: ${ip}. Starting Expo (LAN mode)...`);
  console.log(`   Phone: same Wi-Fi as this laptop. In Expo Go scan the QR code, or enter  exp://${ip}:8081`);
  console.log("   Ctrl+C stops everything.");
  const expo = start("npx expo start --lan --clear --port 8081", [], {
    cwd: APP,
    shell: true,
    stdio: "inherit",
    windowsHide: false,
    env: { ...process.env, REACT_NATIVE_PACKAGER_HOSTNAME: ip }, // Expo would otherwise sometimes pick a VPN/virtual adapter
  });
  expo.on("exit", () => {
    stopAll();
    process.exit(0);
  });
}

process.on("SIGINT", () => {
  say("Stopping backend, tunnel and Expo...");
  stopAll();
  process.exit(0);
});

main().catch((error) => {
  console.error(`\n\x1b[31m${error.message}\x1b[0m`);
  stopAll();
  process.exit(1);
});
