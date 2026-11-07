import assert from "node:assert/strict";
import { mkdtemp, readFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import * as Y from "yjs";
import { markCurrentCatalogAnalyzed } from "../src/analysis/incremental-queue.js";
import { importBackup } from "../src/pipeline.js";

test("imports a backup and creates Codex analysis outputs", async () => {
  const dataDir = await mkdtemp(path.join(os.tmpdir(), "greek-context-test-"));
  const document = new Y.Doc();
  document.getMap("objects").set("frame-1", {
    id: "frame-1",
    type: "frame",
    labelText: "Lesson 1",
  });

  const result = await importBackup({
    dataDir,
    boardId: "test-board",
    backupBytes: Y.encodeStateAsUpdateV2(document),
    source: { kind: "backup", encodingVersion: 2 },
    downloadAssets: false,
  });

  assert.equal(result.stats.totalObjects, 1);
  const queue = JSON.parse(await readFile(path.join(result.boardDir, "analysis", "queue.json"), "utf8"));
  const profile = JSON.parse(await readFile(path.join(result.boardDir, "output", "learner-profile.json"), "utf8"));
  const context = await readFile(path.join(result.boardDir, "output", "chat-context.md"), "utf8");
  const instructions = await readFile(path.join(result.boardDir, "output", "chatgpt-project-instructions.md"), "utf8");
  assert.equal(queue.boardId, "test-board");
  assert.equal(queue.schemaVersion, 2);
  assert.deepEqual(queue.assetItems, []);
  assert.equal(queue.textItems.length, 1);
  assert.equal(profile.status, "awaiting_analysis");
  assert.match(context, /Учебный контекст/);
  assert.match(instructions, /Инструкции для ChatGPT Project/);

  await markCurrentCatalogAnalyzed(result.boardDir);
  await importBackup({
    dataDir,
    boardId: "test-board",
    backupBytes: Y.encodeStateAsUpdateV2(document),
    source: { kind: "backup", encodingVersion: 2 },
    downloadAssets: false,
  });
  const repeatedQueue = JSON.parse(await readFile(path.join(result.boardDir, "analysis", "queue.json"), "utf8"));
  assert.equal(repeatedQueue.textItems.length, 0);
  assert.equal(repeatedQueue.reusedTextItems.length, 0);
  assert.equal(repeatedQueue.summary.unchangedTextItems, 1);
});
