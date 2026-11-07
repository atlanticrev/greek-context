import assert from "node:assert/strict";
import test from "node:test";
import * as Y from "yjs";
import { decodeHolstBackup } from "../src/holst/decode-backup.js";

test("decodes a Yjs V2 Holst-style document", () => {
  const document = new Y.Doc();
  const objects = document.getMap("objects");
  const documents = document.getMap("documents");
  objects.set("frame-1", { id: "frame-1", type: "frame", labelText: "Lesson 1" });
  documents.set("doc-1", "γειά σου");

  const decoded = decodeHolstBackup(Y.encodeStateAsUpdateV2(document));
  assert.equal(decoded.encodingVersion, 2);
  assert.equal(decoded.objects.length, 1);
  assert.equal(decoded.documents["doc-1"], "γειά σου");
});
