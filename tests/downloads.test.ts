import assert from "node:assert/strict";
import { mkdtemp, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { findLatestHolstDownload } from "../src/holst/downloads.js";

test("finds the latest matching recent Holst download", async () => {
  const downloadsDir = await mkdtemp(path.join(os.tmpdir(), "greek-context-downloads-"));
  const filename = path.join(downloadsDir, "Greek Lessons.holst");
  await writeFile(filename, "fixture");
  const result = await findLatestHolstDownload({ downloadsDir, nameIncludes: "Greek", maxAgeMinutes: 5 });
  assert.equal(result, filename);
});

test("rejects stale or missing downloads", async () => {
  const downloadsDir = await mkdtemp(path.join(os.tmpdir(), "greek-context-downloads-"));
  await assert.rejects(() => findLatestHolstDownload({ downloadsDir, maxAgeMinutes: 5 }));
});
