import type { DecodedBoard, JsonValue, NormalizedBoard, NormalizedObject } from "../types.js";

const ASSET_HOST = "storage-edge.app.holst.so";
const ASSET_KEY_PATTERN = /(asset|file|image|media|preview|storage|src|thumbnail|upload|url)/i;

function asRecord(value: JsonValue | undefined): Record<string, JsonValue> | null {
  return value && typeof value === "object" && !Array.isArray(value) ? value : null;
}

function asString(value: JsonValue | undefined): string | null {
  return typeof value === "string" && value.length > 0 ? value : null;
}

function asNumber(value: JsonValue | undefined): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function cleanText(value: string): string | null {
  const text = value.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
  return text || null;
}

function extractText(value: JsonValue | undefined): string | null {
  if (typeof value === "string") {
    return cleanText(value);
  }
  if (Array.isArray(value)) {
    const text = value.map(extractText).filter(Boolean).join(" ").replace(/\s+/g, " ").trim();
    return text || null;
  }
  if (value && typeof value === "object") {
    if (typeof value.text === "string") return cleanText(value.text);
    const childValues = [value.children, value.content, value.value].filter((item): item is JsonValue => item !== undefined);
    const text = childValues.map(extractText).filter(Boolean).join(" ").replace(/\s+/g, " ").trim();
    return text || null;
  }
  return null;
}

function extractJsonStateText(value: JsonValue | undefined): string | null {
  const record = asRecord(value);
  if (!record) return null;
  let children = record.children;
  if (typeof children === "string") {
    const serializedChildren = children;
    try {
      children = JSON.parse(serializedChildren) as JsonValue;
    } catch {
      return cleanText(serializedChildren);
    }
  }
  return extractText(children);
}

function collectAssetUrls(value: JsonValue, keyHint = "", output = new Set<string>()): Set<string> {
  if (typeof value === "string") {
    try {
      const url = new URL(value);
      if (url.hostname === ASSET_HOST && /\/(storage|resize)\//.test(url.pathname)) output.add(url.toString());
    } catch {
      if (ASSET_KEY_PATTERN.test(keyHint) && /^[0-9a-f-]{20,}\.[a-z0-9]{2,5}$/i.test(value)) {
        output.add(`https://${ASSET_HOST}/storage/${value}`);
      }
    }
    return output;
  }

  if (Array.isArray(value)) {
    for (const item of value) collectAssetUrls(item, keyHint, output);
    return output;
  }

  if (value && typeof value === "object") {
    for (const [key, item] of Object.entries(value)) collectAssetUrls(item, key, output);
  }
  return output;
}

function findFrameId(object: Record<string, JsonValue>, byId: Map<string, Record<string, JsonValue>>): string | null {
  let parentId = asString(object.parentId);
  const visited = new Set<string>();
  while (parentId && !visited.has(parentId)) {
    visited.add(parentId);
    const parent = byId.get(parentId);
    if (!parent) return null;
    if (asString(parent.type) === "frame") return parentId;
    parentId = asString(parent.parentId);
  }
  return null;
}

export function normalizeBoard(input: {
  boardId: string;
  decoded: DecodedBoard;
  source: NormalizedBoard["source"];
  observedAssetUrls?: string[];
}): NormalizedBoard {
  const byId = new Map<string, Record<string, JsonValue>>();
  for (const entry of input.decoded.objects) {
    byId.set(asString(entry.value.id) ?? entry.key, entry.value);
  }

  const objects: NormalizedObject[] = input.decoded.objects.map(({ key, value }) => {
    const id = asString(value.id) ?? key;
    const documentId = asString(value.documentId);
    const position = asRecord(value.position);
    const size = asRecord(value.size);
    const documentText = documentId ? extractText(input.decoded.documents[documentId]) : null;
    const labelText = extractText(value.labelText);
    const directText = extractText(value.text);
    const jsonStateText = extractJsonStateText(value.jsonState);

    return {
      id,
      type: asString(value.type) ?? "unknown",
      parentId: asString(value.parentId),
      frameId: asString(value.type) === "frame" ? id : findFrameId(value, byId),
      text: documentText ?? labelText ?? directText ?? jsonStateText,
      position: {
        x: asNumber(position?.x) ?? asNumber(value.x),
        y: asNumber(position?.y) ?? asNumber(value.y),
      },
      size: {
        width: asNumber(size?.width) ?? asNumber(value.width),
        height: asNumber(size?.height) ?? asNumber(value.height),
      },
      assetUrls: [...collectAssetUrls(value)].sort(),
      raw: value,
    };
  });

  const objectById = new Map(objects.map((object) => [object.id, object]));
  const frames = objects
    .filter((object) => object.type === "frame")
    .map((frame) => ({
      id: frame.id,
      label: frame.text,
      childCount: objects.filter((object) => object.frameId === frame.id && object.id !== frame.id).length,
    }))
    .sort((left, right) => (left.label ?? left.id).localeCompare(right.label ?? right.id));

  const assetUrls = new Set(input.observedAssetUrls ?? []);
  for (const object of objects) for (const url of object.assetUrls) assetUrls.add(url);

  const byType: Record<string, number> = {};
  for (const object of objects) byType[object.type] = (byType[object.type] ?? 0) + 1;

  for (const object of objects) {
    if (object.parentId && !objectById.has(object.parentId)) object.frameId = null;
  }

  return {
    schemaVersion: 1,
    boardId: input.boardId,
    generatedAt: new Date().toISOString(),
    source: input.source,
    stats: {
      totalObjects: objects.length,
      totalDocuments: Object.keys(input.decoded.documents).length,
      byType,
      frames: frames.length,
      textObjects: objects.filter((object) => object.text).length,
      assetCandidates: assetUrls.size,
    },
    frames,
    objects,
    assetUrls: [...assetUrls].sort(),
  };
}
