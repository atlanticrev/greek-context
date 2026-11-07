import * as Y from "yjs";
import type { DecodedBoard, JsonValue } from "../types.js";

function toJsonValue(value: unknown): JsonValue {
  if (value === null || typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
    return value;
  }

  if (value && typeof value === "object" && "toJSON" in value && typeof value.toJSON === "function") {
    return toJsonValue(value.toJSON());
  }

  if (Array.isArray(value)) {
    return value.map(toJsonValue);
  }

  if (value instanceof Map) {
    return Object.fromEntries([...value.entries()].map(([key, item]) => [String(key), toJsonValue(item)]));
  }

  if (value && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value as Record<string, unknown>).map(([key, item]) => [key, toJsonValue(item)]),
    );
  }

  return String(value);
}

function decodeWithVersion(bytes: Uint8Array, encodingVersion: 1 | 2): DecodedBoard {
  const doc = new Y.Doc();
  if (encodingVersion === 2) {
    Y.applyUpdateV2(doc, bytes);
  } else {
    Y.applyUpdate(doc, bytes);
  }

  const objectsMap = doc.getMap("objects");
  const documentsMap = doc.getMap("documents");
  const objects: DecodedBoard["objects"] = [];
  const documents: Record<string, JsonValue> = {};

  objectsMap.forEach((value, key) => {
    const json = toJsonValue(value);
    const record = json && typeof json === "object" && !Array.isArray(json) ? json : { value: json };
    objects.push({ key, value: record as Record<string, JsonValue> });
  });

  documentsMap.forEach((value, key) => {
    documents[key] = toJsonValue(value);
  });

  return {
    encodingVersion,
    rootNames: [...doc.share.keys()].sort(),
    objects,
    documents,
  };
}

export function decodeHolstBackup(bytes: Uint8Array, preferredVersion?: 1 | 2): DecodedBoard {
  const versions: Array<1 | 2> = preferredVersion ? [preferredVersion] : [2, 1];
  const successes: DecodedBoard[] = [];
  const errors: string[] = [];

  for (const version of versions) {
    try {
      successes.push(decodeWithVersion(bytes, version));
    } catch (error) {
      errors.push(`Yjs V${version}: ${error instanceof Error ? error.message : String(error)}`);
    }
  }

  const best = successes.sort(
    (left, right) => right.objects.length + Object.keys(right.documents).length - (left.objects.length + Object.keys(left.documents).length),
  )[0];

  if (!best || (best.objects.length === 0 && Object.keys(best.documents).length === 0)) {
    throw new Error(`Could not decode Holst backup. ${errors.join("; ")}`);
  }

  return best;
}
