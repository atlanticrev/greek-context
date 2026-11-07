import assert from "node:assert/strict";
import test from "node:test";
import { normalizeBoard } from "../src/holst/normalize-objects.js";

test("normalizes hierarchy, text, and asset URLs", () => {
  const board = normalizeBoard({
    boardId: "board-1",
    decoded: {
      encodingVersion: 2,
      rootNames: ["documents", "objects"],
      documents: { "doc-1": "ο μαθητής" },
      objects: [
        { key: "frame-1", value: { id: "frame-1", type: "frame", labelText: "Lesson 1" } },
        {
          key: "image-1",
          value: {
            id: "image-1",
            type: "image",
            parentId: "frame-1",
            documentId: "doc-1",
            imageUrl: "https://storage-edge.app.holst.so/storage/example.png",
          },
        },
      ],
    },
    source: { kind: "backup", encodingVersion: 2 },
  });

  assert.equal(board.frames[0]?.childCount, 1);
  assert.equal(board.objects[1]?.frameId, "frame-1");
  assert.equal(board.objects[1]?.text, "ο μαθητής");
  assert.deepEqual(board.assetUrls, ["https://storage-edge.app.holst.so/storage/example.png"]);
});
