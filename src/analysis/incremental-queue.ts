import { createHash } from "node:crypto";
import { readFile, writeFile } from "node:fs/promises";
import path from "node:path";

export interface AnalysisTextItem {
  objectId: string;
  frameId: string | null;
  objectType: string;
  text: string;
  contentHash: string;
}

export interface AnalysisAssetItem {
  id: string;
  assetPath: string;
  sha256: string | null;
  sourceUrl: string;
  contentType: string | null;
  kind: "audio" | "image";
  relatedObjectIds: string[];
  contentKey: string;
}

export interface AnalysisCatalog {
  schemaVersion: 1;
  boardId: string;
  generatedAt: string;
  textItems: AnalysisTextItem[];
  assetItems: AnalysisAssetItem[];
}

export interface IncrementalAnalysisQueue {
  schemaVersion: 2;
  boardId: string;
  generatedAt: string;
  instructions: string[];
  summary: {
    currentTextItems: number;
    currentUniqueTextContents: number;
    newOrChangedTextItems: number;
    reusedTextReferences: number;
    unchangedTextItems: number;
    currentUniqueAssets: number;
    newAssets: number;
    reusedAssetReferences: number;
    unchangedAssets: number;
    removedTextItems: number;
    removedAssets: number;
  };
  textItems: Array<AnalysisTextItem & { changeType: "new" | "changed" }>;
  reusedTextItems: Array<{
    objectId: string;
    frameId: string | null;
    objectType: string;
    contentHash: string;
    matchesObjectId: string;
    reason: "duplicate_in_current_board" | "previously_analyzed_content" | "reference_moved";
  }>;
  assetItems: Array<AnalysisAssetItem & { changeType: "new" }>;
  reusedAssetItems: Array<{
    id: string;
    assetPath: string;
    sha256: string | null;
    contentKey: string;
    previousAssetPath: string;
    newRelatedObjectIds: string[];
  }>;
  removedTextObjectIds: string[];
  removedAssetContentKeys: string[];
}

function hashText(objectType: string, text: string): string {
  return createHash("sha256").update(JSON.stringify([objectType, text])).digest("hex");
}

export function createAnalysisCatalog(input: {
  boardId: string;
  textItems: Array<Omit<AnalysisTextItem, "contentHash">>;
  assetItems: Array<Omit<AnalysisAssetItem, "contentKey">>;
}): AnalysisCatalog {
  const assetByContent = new Map<string, AnalysisAssetItem>();
  for (const item of input.assetItems) {
    const contentKey = item.sha256 ?? item.sourceUrl;
    const existing = assetByContent.get(contentKey);
    if (existing) {
      existing.relatedObjectIds = [...new Set([...existing.relatedObjectIds, ...item.relatedObjectIds])].sort();
      continue;
    }
    assetByContent.set(contentKey, {
      ...item,
      relatedObjectIds: [...new Set(item.relatedObjectIds)].sort(),
      contentKey,
    });
  }

  return {
    schemaVersion: 1,
    boardId: input.boardId,
    generatedAt: new Date().toISOString(),
    textItems: input.textItems.map((item) => ({
      ...item,
      contentHash: hashText(item.objectType, item.text),
    })),
    assetItems: [...assetByContent.values()],
  };
}

async function readAnalyzedCatalog(analysisDir: string): Promise<AnalysisCatalog | null> {
  try {
    return JSON.parse(await readFile(path.join(analysisDir, "analyzed-catalog.json"), "utf8")) as AnalysisCatalog;
  } catch (error) {
    const code = (error as NodeJS.ErrnoException).code;
    if (code === "ENOENT") return null;
    throw error;
  }
}

export async function writeIncrementalAnalysisQueue(input: {
  analysisDir: string;
  catalog: AnalysisCatalog;
  instructions: string[];
}): Promise<IncrementalAnalysisQueue> {
  const previous = await readAnalyzedCatalog(input.analysisDir);
  const previousTextById = new Map(previous?.textItems.map((item) => [item.objectId, item]) ?? []);
  const previousTextByContent = new Map<string, AnalysisTextItem>();
  for (const item of previous?.textItems ?? []) {
    if (!previousTextByContent.has(item.contentHash)) previousTextByContent.set(item.contentHash, item);
  }

  const textItems: IncrementalAnalysisQueue["textItems"] = [];
  const reusedTextItems: IncrementalAnalysisQueue["reusedTextItems"] = [];
  const queuedTextByContent = new Map<string, AnalysisTextItem>();

  for (const item of input.catalog.textItems) {
    const previousById = previousTextById.get(item.objectId);
    if (previousById?.contentHash === item.contentHash && previousById.frameId === item.frameId) continue;

    if (previousById && previousById.contentHash !== item.contentHash) {
      textItems.push({ ...item, changeType: "changed" });
      if (!queuedTextByContent.has(item.contentHash)) queuedTextByContent.set(item.contentHash, item);
      continue;
    }

    const previousMatch = previousTextByContent.get(item.contentHash);
    const currentMatch = queuedTextByContent.get(item.contentHash);
    const match = previousMatch ?? currentMatch;
    if (match) {
      reusedTextItems.push({
        objectId: item.objectId,
        frameId: item.frameId,
        objectType: item.objectType,
        contentHash: item.contentHash,
        matchesObjectId: match.objectId,
        reason: previousById
          ? "reference_moved"
          : previousMatch
            ? "previously_analyzed_content"
            : "duplicate_in_current_board",
      });
      continue;
    }

    textItems.push({ ...item, changeType: "new" });
    queuedTextByContent.set(item.contentHash, item);
  }

  const previousAssets = new Map(previous?.assetItems.map((item) => [item.contentKey, item]) ?? []);
  const assetItems: IncrementalAnalysisQueue["assetItems"] = [];
  const reusedAssetItems: IncrementalAnalysisQueue["reusedAssetItems"] = [];
  for (const item of input.catalog.assetItems) {
    const prior = previousAssets.get(item.contentKey);
    if (!prior) {
      assetItems.push({ ...item, changeType: "new" });
      continue;
    }
    const priorObjectIds = new Set(prior.relatedObjectIds);
    const newRelatedObjectIds = item.relatedObjectIds.filter((objectId) => !priorObjectIds.has(objectId));
    if (newRelatedObjectIds.length > 0) {
      reusedAssetItems.push({
        id: item.id,
        assetPath: item.assetPath,
        sha256: item.sha256,
        contentKey: item.contentKey,
        previousAssetPath: prior.assetPath,
        newRelatedObjectIds,
      });
    }
  }

  const currentTextIds = new Set(input.catalog.textItems.map((item) => item.objectId));
  const removedTextObjectIds = (previous?.textItems ?? [])
    .map((item) => item.objectId)
    .filter((objectId) => !currentTextIds.has(objectId));
  const currentAssetKeys = new Set(input.catalog.assetItems.map((item) => item.contentKey));
  const removedAssetContentKeys = (previous?.assetItems ?? [])
    .map((item) => item.contentKey)
    .filter((contentKey) => !currentAssetKeys.has(contentKey));

  const queue: IncrementalAnalysisQueue = {
    schemaVersion: 2,
    boardId: input.catalog.boardId,
    generatedAt: new Date().toISOString(),
    instructions: input.instructions,
    summary: {
      currentTextItems: input.catalog.textItems.length,
      currentUniqueTextContents: new Set(input.catalog.textItems.map((item) => item.contentHash)).size,
      newOrChangedTextItems: textItems.length,
      reusedTextReferences: reusedTextItems.length,
      unchangedTextItems: input.catalog.textItems.length - textItems.length - reusedTextItems.length,
      currentUniqueAssets: input.catalog.assetItems.length,
      newAssets: assetItems.length,
      reusedAssetReferences: reusedAssetItems.reduce((total, item) => total + item.newRelatedObjectIds.length, 0),
      unchangedAssets: input.catalog.assetItems.length - assetItems.length - reusedAssetItems.length,
      removedTextItems: removedTextObjectIds.length,
      removedAssets: removedAssetContentKeys.length,
    },
    textItems,
    reusedTextItems,
    assetItems,
    reusedAssetItems,
    removedTextObjectIds,
    removedAssetContentKeys,
  };

  await writeFile(path.join(input.analysisDir, "catalog.json"), `${JSON.stringify(input.catalog, null, 2)}\n`);
  await writeFile(path.join(input.analysisDir, "queue.json"), `${JSON.stringify(queue, null, 2)}\n`);
  return queue;
}

export async function markCurrentCatalogAnalyzed(boardDir: string): Promise<string> {
  const analysisDir = path.join(boardDir, "analysis");
  const catalogPath = path.join(analysisDir, "catalog.json");
  const catalog = JSON.parse(await readFile(catalogPath, "utf8")) as AnalysisCatalog;
  const target = path.join(analysisDir, "analyzed-catalog.json");
  await writeFile(target, `${JSON.stringify(catalog, null, 2)}\n`);
  return target;
}
