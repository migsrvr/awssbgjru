const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

// Mock browser globals needed by admin.js during require
global.window = {
  location: { hostname: "localhost" },
};
global.document = {
  getElementById: () => null,
  querySelectorAll: () => [],
  addEventListener: () => {},
};
global.sessionStorage = {
  getItem: () => null,
  setItem: () => {},
  removeItem: () => {},
};
global.localStorage = {
  getItem: () => null,
  setItem: () => {},
  removeItem: () => {},
};

const {
  QR_ASSETS,
  getDivisionQrConfig,
  loadQrDataUrl,
  qrDataUrlCache,
} = require("../frontend/js/admin.js");

test("QR_ASSETS contains expected static asset paths", () => {
  assert.equal(QR_ASSETS.general, "/assets/QRs/GeneralQR.png");
  assert.equal(QR_ASSETS.relations, "/assets/QRs/RelationsQR.png");
  assert.equal(QR_ASSETS.operations, "/assets/QRs/OperationalQR.png");
  assert.equal(QR_ASSETS.creatives, "/assets/QRs/CreativesQR.png");
});

test("all referenced QR asset files physically exist on disk in frontend/assets/QRs", () => {
  const rootDir = path.resolve(__dirname, "..");
  for (const [key, webPath] of Object.entries(QR_ASSETS)) {
    const filePath = path.join(rootDir, "frontend", webPath);
    assert.ok(
      fs.existsSync(filePath),
      `Expected QR asset file to exist at ${filePath} for key '${key}'`
    );
    const stat = fs.statSync(filePath);
    assert.ok(stat.size > 1000, `QR file ${filePath} should have non-trivial size, got ${stat.size} bytes`);
  }
});

test("getDivisionQrConfig correctly maps Relations division variants", () => {
  const cases = ["Relations", "Relations Office", "Relations Department", "Public Relations"];
  for (const div of cases) {
    const config = getDivisionQrConfig(div);
    assert.ok(config, `Should resolve config for ${div}`);
    assert.equal(config.path, "/assets/QRs/RelationsQR.png");
    assert.equal(config.label, "Relations QR Attached");
  }
});

test("getDivisionQrConfig correctly maps Operations division variants", () => {
  const cases = ["Operations", "Operations Office", "Operations Department"];
  for (const div of cases) {
    const config = getDivisionQrConfig(div);
    assert.ok(config, `Should resolve config for ${div}`);
    assert.equal(config.path, "/assets/QRs/OperationalQR.png");
    assert.equal(config.label, "Operations QR Attached");
  }
});

test("getDivisionQrConfig correctly maps Creatives and Media division variants", () => {
  const cases = ["Creatives", "Creatives Department", "Media", "Design & Media"];
  for (const div of cases) {
    const config = getDivisionQrConfig(div);
    assert.ok(config, `Should resolve config for ${div}`);
    assert.equal(config.path, "/assets/QRs/CreativesQR.png");
    assert.equal(config.label, "Creatives QR Attached");
  }
});

test("getDivisionQrConfig returns null for divisions without pre-defined QR files", () => {
  const cases = [
    "Technology",
    "Marketing",
    "Finance",
    "Software Development",
    "Web Development",
    "UI/UX",
    "Cloud Computing",
    "Data Analyst",
    "",
    null,
    undefined,
  ];
  for (const div of cases) {
    const config = getDivisionQrConfig(div);
    assert.equal(config, null, `Expected null QR config for '${div}'`);
  }
});

test("loadQrDataUrl caches data URLs once loaded", async () => {
  qrDataUrlCache["/test/path.png"] = "data:image/png;base64,TEST_DATA";
  const result = await loadQrDataUrl("/test/path.png");
  assert.equal(result, "data:image/png;base64,TEST_DATA");
});
