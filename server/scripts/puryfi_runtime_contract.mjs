#!/usr/bin/env node
/**
 * Contract checks executed against the real PuryFi plugin handler shipped in
 * the latest XPI under purify-sdk/versions-built/.
 *
 * The XPI is a browser extension bundle. This script extracts the webpack
 * module `./dist/background/plugin-handler.js` from
 * background/background.bundle.js and executes its actual `handleMessage`
 * logic in Node with a minimal mocked extension state. It also instantiates
 * the real plugin connection class to verify the `ready` handshake and the
 * pre-ready gating.
 *
 * Usage:
 *   node server/scripts/puryfi_runtime_contract.mjs
 *
 * Requires: `unzip`, Node.js 22+.
 */

import { execFileSync } from "node:child_process";
import { existsSync, readdirSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
const VERSIONS_DIR = join(ROOT, "purify-sdk", "versions-built");

function fail(message) {
  console.error(`ERROR: ${message}`);
  process.exit(2);
}

function parseVersion(filename) {
  const match = filename.match(/(\d+)\.(\d+)\.(\d+)/);
  return match ? match.slice(1).map(Number) : [0, 0, 0];
}

function pickLatestXpi() {
  if (!existsSync(VERSIONS_DIR)) {
    fail(`versions directory not found: ${VERSIONS_DIR}`);
  }
  const files = readdirSync(VERSIONS_DIR)
    .filter((name) => name.endsWith(".xpi"))
    .map((name) => ({ name, version: parseVersion(name) }))
    .sort((a, b) => {
      for (let i = 0; i < 3; i += 1) {
        if (a.version[i] !== b.version[i]) return b.version[i] - a.version[i];
      }
      return a.name.localeCompare(b.name);
    });

  if (files.length === 0) {
    fail(`no .xpi found in ${VERSIONS_DIR}`);
  }
  return join(VERSIONS_DIR, files[0].name);
}

function readXpiMember(xpi, member) {
  return execFileSync("unzip", ["-p", xpi, member], {
    maxBuffer: 32 * 1024 * 1024,
  }).toString("utf8");
}

function extractModule(bundle, key) {
  const marker = `"${key}"(e,t,n)`;
  const start = bundle.indexOf(marker);
  if (start < 0) throw new Error(`module not found in bundle: ${key}`);

  const bodyStart = start + marker.length;
  // The next webpack module starts at `,"<path>"(e,t,n){`.
  const nextModule = /,"([^"]+)"\(e,t,n\)\{/g;
  nextModule.lastIndex = bodyStart;
  const next = nextModule.exec(bundle);

  const end = next ? next.index : bundle.length;
  let body = bundle.slice(bodyStart, end);
  body = body.slice(0, body.lastIndexOf("}") + 1);

  // Make sure the extracted body is still valid JavaScript.
  new Function("e", "t", "n", body);
  return body;
}

function makeRequire(resolveModule) {
  const require = (id) => resolveModule(id);
  require.r = (exports) => {
    if (typeof Symbol !== "undefined" && Symbol.toStringTag) {
      Object.defineProperty(exports, Symbol.toStringTag, { value: "Module" });
    }
    Object.defineProperty(exports, "__esModule", { value: true });
  };
  require.d = (exports, definitions) => {
    for (const key in definitions) {
      if (!(key in exports)) {
        Object.defineProperty(exports, key, {
          enumerable: true,
          get: definitions[key],
        });
      }
    }
  };
  require.o = (object, key) => Object.prototype.hasOwnProperty.call(object, key);
  require.g = globalThis;
  return require;
}

function loadModule(bundle, key, resolveModule) {
  const module = { exports: {} };
  const body = extractModule(bundle, key);
  const fn = new Function("e", "t", "n", body);
  fn(module, module.exports, makeRequire(resolveModule));
  return module.exports;
}

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

const results = [];

async function test(name, fn) {
  try {
    await fn();
    results.push({ name, ok: true });
    console.log(`[PASS] ${name}`);
  } catch (error) {
    results.push({ name, ok: false, error: error.message });
    console.log(`[FAIL] ${name}: ${error.message}`);
  }
}

function makeState(overrides = {}) {
  return {
    enabled: false,
    lockConfiguration: null,
    wblistConfiguration: {
      mode: "whitelist",
      whitelist: [],
      blacklist: [],
    },
    user: {
      username: "contract-user",
      supportTier: { level: null, name: "No tier" },
    },
    purevision: { connected: 0 },
    ...overrides,
  };
}

function makeLockState() {
  return {
    password: { secret: "old-secret" },
    timer: { endTime: 123456 },
    timerPlus: { timesPerLabel: { 2: 5 } },
    emergencyClientToken: "old-token",
    startTime: 1000,
  };
}

function makeStoredLockConfig() {
  return {
    enabled: true,
    password_enabled: true,
    password: "old-secret",
    timer_enabled: true,
    timer_mode: 0,
    timestamp: 1000,
    duration: 122456,
    duration_timestamp: 1000,
    timer_plus: true,
    timer_plus_data: { 2: 5 },
    token: "old-token",
  };
}

function decodeSent(frame) {
  return JSON.parse(Buffer.from(frame).toString("utf8"));
}

async function main() {
  const xpi = pickLatestXpi();
  const manifest = JSON.parse(readXpiMember(xpi, "manifest.json"));
  const bundle = readXpiMember(xpi, "background/background.bundle.js");

  console.log(`PuryFi runtime: ${manifest.version} (${xpi})`);

  // ---------------------------------------------------------------------
  // Mock the extension environment used by the shipped plugin handler.
  // ---------------------------------------------------------------------
  globalThis.chrome = {
    runtime: { getURL: () => "about:blank" },
    offscreen: {},
  };

  const config = {
    extensionActive: false,
    instanceId: "contract-instance",
    lock_configuration: {
      enabled: false,
      password_enabled: false,
      password: "",
      timer_enabled: false,
      timer_mode: 0,
      timestamp: 0,
      duration: 0,
      duration_timestamp: 0,
      timer_plus: false,
      timer_plus_data: {},
      token: 0,
    },
    whiteblacklist_configuration: {
      mode: 0,
      white_list: [],
      black_list: [],
    },
    default_lock_configuration: {},
    plugins: [],
    PluginConnectionParametersType: {
      External: "external",
      BrowserExtension: "browser-extension",
    },
    LOCK_SALT: "contract-salt",
    LABELS: {},
    hashFnv32a: (value) => `hash:${value}`,
    generateSecurityToken: (seed) => `token:${seed}`,
    testLockEmergencyServerToken: (token, expected) => token === expected,
    isProcessableImageType: () => false,
    setPlugins(value) {
      config.plugins = value;
    },
    setExtensionActive(value) {
      config.extensionActive = value;
    },
    setLockConfiguration(value) {
      config.lock_configuration = value;
    },
    setWhiteblacklistConfiguration(value) {
      config.whiteblacklist_configuration = value;
    },
  };

  const extension = {
    extension: {
      runtime: {
        getManifest: () => ({ version: manifest.version }),
      },
      storage: {
        onChanged: { addListener: () => {} },
        session: { set: async () => {}, get: async () => ({}) },
        sync: { set: async () => {}, get: async () => ({}) },
        local: { set: async () => {}, get: async () => ({}) },
      },
    },
  };

  const content = {
    klasses: {},
    parseEntryFromIndex: (index) => index,
  };

  const mocks = {
    ".": {},
    "./dist/background/configuration.js": config,
    "./dist/common/config.js": config,
    "./dist/common/extension.js": extension,
    "./dist/background/account.js": { user: null },
    "./dist/common/util/object-util.js": {
      isDeepEqual: (a, b) => JSON.stringify(a) === JSON.stringify(b),
    },
    "./dist/common/api.js": { messageOptionsPage: () => {} },
    "./dist/common/object.js": {},
    "./dist/background/listener.js": {},
    "./dist/common/censoring-module.js": {},
    "./dist/common/plugin-connection-description.js": {
      isClientPluginConnectionCloseReason: () => false,
    },
    "./dist/background/purevision-connection.js": {
      PureVisionConnection: { state: { status: 0 } },
    },
    "./dist/common/mimetools.js": {},
    "./dist/common/image.js": {},
    "./dist/common/detections.js": {},
    "./dist/common/canvas.js": {},
    "./dist/common/content.js": content,
    "./dist/common/util.js": {
      hashFnv32a: (value) => `hash:${value}`,
    },
    "./node_modules/@msgpack/msgpack/dist.esm/encode.mjs": {
      encode: (value) => new TextEncoder().encode(JSON.stringify(value)),
    },
    "./node_modules/@msgpack/msgpack/dist.esm/decode.mjs": {
      decode: (value) => JSON.parse(Buffer.from(value).toString("utf8")),
    },
  };

  // Load the SDK modules embedded in the XPI so the handler uses the exact
  // PluginIntents and StateAccess shipped with this PuryFi build.
  const sdkIntents = loadModule(
    bundle,
    "../PuryFi-Plugin-SDK/dist/esm/core/plugin-intent.js",
    () => {
      throw new Error("unexpected SDK dependency");
    },
  );
  const sdkState = loadModule(
    bundle,
    "../PuryFi-Plugin-SDK/dist/esm/core/state.js",
    () => {
      throw new Error("unexpected SDK dependency");
    },
  );
  mocks["../PuryFi-Plugin-SDK/dist/esm/core/index.js"] = {
    PluginIntents: sdkIntents.PluginIntents,
    StateAccess: sdkState.StateAccess,
  };

  const handlerKey = "./dist/background/plugin-handler.js";
  let handlerBody = extractModule(bundle, handlerKey);
  // Test-only export of the internal connection class. The shipped logic is
  // untouched; this only exposes W so the handshake can be exercised.
  handlerBody =
    handlerBody.slice(0, -1) +
    ";n.d(t,{__testConnection:()=>W});}";

  const handlerModule = { exports: {} };
  new Function("e", "t", "n", handlerBody)(
    handlerModule,
    handlerModule.exports,
    makeRequire((id) => mocks[id]),
  );

  const initPluginHandler = handlerModule.exports.initPluginHandler;
  initPluginHandler();
  const handler = handlerModule.exports.pluginHandler;
  const TestConnection = handlerModule.exports.__testConnection;

  const plugin = {
    id: "contract-plugin",
    enabled: true,
    intents: [
      "writeEnabledState",
      "writeLockConfigurationState",
      "readUserState",
      "readMediaProcesses",
    ],
    pendingIntents: [],
    configuration: null,
    manifest: null,
    connectionParameters: {
      type: "external",
      url: "ws://localhost:65535",
    },
  };
  config.plugins = [plugin];

  // ---------------------------------------------------------------------
  // Contract checks on the real plugin handler.
  // ---------------------------------------------------------------------

  await test("getState user.username retourne la valeur d'état", async () => {
    handler.state = makeState();
    const response = await handler.handleMessage("contract-plugin", {
      type: "getState",
      payload: { path: "user.username" },
    });
    assert(response.type === "ok", "response must be ok");
    assert(
      response.value === "contract-user",
      `unexpected value: ${response.value}`,
    );
  });

  await test("setPluginManifest valide le manifest et le restitue", async () => {
    handler.state = makeState();
    const sent = await handler.handleMessage("contract-plugin", {
      type: "setPluginManifest",
      payload: {
        manifest: {
          name: "Contract",
          version: "1.0.0",
          description: "contract",
          author: "tester",
          website: "https://example.invalid",
        },
      },
    });
    assert(sent.type === "ok", "setPluginManifest must succeed");
    const fetched = await handler.handleMessage("contract-plugin", {
      type: "getPluginManifest",
      payload: {},
    });
    assert(fetched.type === "ok", "getPluginManifest must succeed");
    assert(fetched.manifest.name === "Contract", "manifest must be stored");
  });

  await test("setPluginConfiguration accepte une configuration vide", async () => {
    handler.state = makeState();
    const response = await handler.handleMessage("contract-plugin", {
      type: "setPluginConfiguration",
      payload: { configuration: {} },
    });
    assert(response.type === "ok", "configuration must be accepted");
  });

  await test("erreur d'intent manquant utilise la clé 'error'", async () => {
    handler.state = makeState();
    const originalIntents = plugin.intents;
    plugin.intents = [];
    try {
      const response = await handler.handleMessage("contract-plugin", {
        type: "setState",
        payload: { path: "enabled", value: true },
      });
      assert(response.type === "error", "response must be an error");
      assert(
        response.error === "missingPluginIntents",
        `unexpected error key/value: ${JSON.stringify(response)}`,
      );
      assert(
        !("name" in response),
        "runtime errors must not use the SDK 'name' key",
      );
    } finally {
      plugin.intents = originalIntents;
    }
  });

  await test("enterLockPassword sans intent utilise aussi 'error'", async () => {
    handler.state = makeState({ lockConfiguration: makeLockState() });
    const originalIntents = plugin.intents;
    plugin.intents = [];
    try {
      const response = await handler.handleMessage("contract-plugin", {
        type: "enterLockPassword",
        payload: { secret: "old-secret" },
      });
      assert(response.type === "error", "response must be an error");
      assert(
        response.error === "missingPluginIntents",
        `unexpected error: ${JSON.stringify(response)}`,
      );
    } finally {
      plugin.intents = originalIntents;
    }
  });

  await test("setState lockConfiguration partiel efface timer/timerPlus", async () => {
    handler.state = makeState({ lockConfiguration: makeLockState() });
    handler.connections = [];
    config.lock_configuration = makeStoredLockConfig();

    const response = await handler.handleMessage("contract-plugin", {
      type: "setState",
      payload: {
        path: "lockConfiguration",
        value: { password: { secret: "new-secret" } },
      },
    });

    assert(response.type === "ok", "setState must succeed");
    assert(
      handler.state.lockConfiguration.timer === undefined,
      "timer must be removed by the partial payload",
    );
    assert(
      handler.state.lockConfiguration.timerPlus === undefined,
      "timerPlus must be removed by the partial payload",
    );
    assert(
      config.lock_configuration.timer_enabled === false,
      "stored timer_enabled must be false",
    );
    assert(
      config.lock_configuration.timer_plus === false,
      "stored timer_plus must be false",
    );
  });

  await test("setState lockConfiguration complet conserve timer/timerPlus", async () => {
    handler.state = makeState({ lockConfiguration: makeLockState() });
    handler.connections = [];
    config.lock_configuration = makeStoredLockConfig();

    const response = await handler.handleMessage("contract-plugin", {
      type: "setState",
      payload: {
        path: "lockConfiguration",
        value: {
          password: { secret: "new-secret" },
          timer: { endTime: 123456 },
          timerPlus: { timesPerLabel: { 2: 5 } },
        },
      },
    });

    assert(response.type === "ok", "setState must succeed");
    assert(
      handler.state.lockConfiguration.timer?.endTime === 123456,
      "timer must be preserved",
    );
    assert(
      handler.state.lockConfiguration.timerPlus?.timesPerLabel?.[2] === 5,
      "timerPlus must be preserved",
    );
    assert(
      config.lock_configuration.timer_enabled === true,
      "stored timer_enabled must be true",
    );
    assert(
      config.lock_configuration.timer_plus === true,
      "stored timer_plus must be true",
    );
  });

  await test("enterLockPassword valide le secret et supprime le lock", async () => {
    handler.state = makeState({ lockConfiguration: makeLockState() });
    handler.connections = [];
    // The mock hash function returns "hash:<secret>"; the runtime stores the
    // hashed secret, so the state must contain it.
    handler.state.lockConfiguration.password.secret = "hash:old-secret";
    const response = await handler.handleMessage("contract-plugin", {
      type: "enterLockPassword",
      payload: { secret: "old-secret" },
    });
    assert(response.type === "ok", `unexpected response: ${JSON.stringify(response)}`);
    assert(
      handler.state.lockConfiguration === null,
      "lockConfiguration must be cleared",
    );
  });

  await test("subscribeToStaticMediaScans exige readMediaProcesses", async () => {
    handler.state = makeState();
    handler.connections = [
      {
        plugin,
        data: {
          type: "open",
          isReady: true,
          isSubscribedToStaticMediaScans: false,
          subscribedToState: new Set(),
        },
      },
    ];
    const originalIntents = plugin.intents;
    plugin.intents = ["readUserState"];
    try {
      const denied = await handler.handleMessage("contract-plugin", {
        type: "subscribeToStaticMediaScans",
        payload: {},
      });
      assert(
        denied.type === "error" && denied.error === "missingPluginIntents",
        "subscription must be denied without readMediaProcesses",
      );
    } finally {
      plugin.intents = originalIntents;
    }

    const allowed = await handler.handleMessage("contract-plugin", {
      type: "subscribeToStaticMediaScans",
      payload: {},
    });
    assert(allowed.type === "ok", "subscription must be accepted with the intent");
    assert(
      handler.connections[0].data.isSubscribedToStaticMediaScans === true,
      "subscription flag must be set",
    );
  });

  // ---------------------------------------------------------------------
  // Real connection class: ready frame and pre-ready gating.
  // ---------------------------------------------------------------------

  class FakeWebSocket {
    static instances = [];
    constructor(url) {
      this.url = url;
      this.sent = [];
      FakeWebSocket.instances.push(this);
    }
    send(data) {
      this.sent.push(data);
    }
    close() {
      this.onclose?.({});
    }
  }
  globalThis.WebSocket = FakeWebSocket;

  await test("ready est envoyé avec apiVersion 1.0.0", async () => {
    handler.connections = [];
    let handled = 0;
    const connection = new TestConnection(
      { ...plugin, connectionParameters: { type: "external", url: "ws://localhost:65534" } },
      () => {},
      async () => {
        handled += 1;
        return { type: "ok" };
      },
    );
    const socket = FakeWebSocket.instances.at(-1);
    socket.onopen();
    assert(connection.data.type === "open", "connection must be open");
    assert(socket.sent.length === 1, "ready frame must be sent");
    const frame = decodeSent(socket.sent[0]);
    assert(frame.type === "ready", "first frame must be ready");
    assert(
      frame.payload.apiVersion === "1.0.0",
      `unexpected apiVersion: ${frame.payload.apiVersion}`,
    );
    assert(
      frame.payload.version === manifest.version.replace("B", ""),
      `unexpected runtime version: ${frame.payload.version}`,
    );
    assert(typeof frame.responseId === "number", "ready must carry a responseId");
    if (connection.data.readyMessageResponseTimeout) {
      clearTimeout(connection.data.readyMessageResponseTimeout);
    }
    connection.data.type = "closed";
    assert(handled === 0, "no plugin message must be handled before isReady");
  });

  await test("les messages du plugin sont ignorés avant isReady", async () => {
    handler.connections = [];
    let handled = 0;
    const connection = new TestConnection(
      { ...plugin, connectionParameters: { type: "external", url: "ws://localhost:65533" } },
      () => {},
      async () => {
        handled += 1;
        return { type: "ok" };
      },
    );
    const socket = FakeWebSocket.instances.at(-1);
    socket.onopen();
    connection.data.isReady = false;
    await connection.handleEncodedMessage(
      Buffer.from(
        JSON.stringify({
          type: "setState",
          payload: { path: "enabled", value: true },
          responseId: 1,
        }),
      ),
    );
    assert(handled === 0, "pre-ready message must be ignored");

    connection.data.isReady = true;
    await connection.handleEncodedMessage(
      Buffer.from(
        JSON.stringify({
          type: "setState",
          payload: { path: "enabled", value: true },
          responseId: 2,
        }),
      ),
    );
    assert(handled === 1, "post-ready message must be handled");
    if (connection.data.readyMessageResponseTimeout) {
      clearTimeout(connection.data.readyMessageResponseTimeout);
    }
    connection.data.type = "closed";
  });

  // ---------------------------------------------------------------------
  // Summary.
  // ---------------------------------------------------------------------
  const failed = results.filter((result) => !result.ok);
  console.log("");
  console.log(`Résultat: ${results.length - failed.length}/${results.length} tests passés`);
  for (const result of failed) {
    console.log(`  - ${result.name}: ${result.error}`);
  }
  process.exit(failed.length === 0 ? 0 : 1);
}

main().catch((error) => {
  console.error(error);
  process.exit(2);
});
