import assert from "node:assert/strict";
import test from "node:test";
import { parseBoardUrl } from "../src/holst/url.js";

test("parses a Holst board URL", () => {
  const result = parseBoardUrl("https://app.holst.so/board/00000000-0000-4000-8000-000000000001?x=1");
  assert.equal(result.boardId, "00000000-0000-4000-8000-000000000001");
  assert.equal(result.url, "https://app.holst.so/board/00000000-0000-4000-8000-000000000001");
});

test("rejects a non-Holst host", () => {
  assert.throws(() => parseBoardUrl("https://example.com/board/00000000-0000-4000-8000-000000000001"));
});
