import { createHash } from "node:crypto";
import { copyFile, mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { createAnalysisCatalog, writeIncrementalAnalysisQueue } from "./analysis/incremental-queue.js";
import { downloadBoardAssets } from "./holst/assets.js";
import { isHolstArchive, readHolstArchive } from "./holst/archive.js";
import { decodeHolstBackup } from "./holst/decode-backup.js";
import { normalizeBoard } from "./holst/normalize-objects.js";
import { buildLearnerProfile } from "./profile/build-profile.js";
import type { NormalizedBoard } from "./types.js";

export interface ImportResult {
  boardDir: string;
  normalizedPath: string;
  assetsDownloaded: number;
  assetsReused: number;
  assetsFailed: number;
  analysis: {
    newOrChangedTextItems: number;
    reusedTextReferences: number;
    newAssets: number;
    reusedAssetReferences: number;
  };
  stats: NormalizedBoard["stats"];
}

export async function importBackup(input: {
  dataDir: string;
  boardId: string;
  backupPath?: string;
  backupBytes?: Uint8Array;
  source: NormalizedBoard["source"];
  observedAssetUrls?: string[];
  downloadAssets?: boolean;
  preferredEncodingVersion?: 1 | 2;
}): Promise<ImportResult> {
  const boardDir = path.resolve(input.dataDir, "boards", input.boardId);
  const rawDir = path.join(boardDir, "raw");
  const normalizedDir = path.join(boardDir, "normalized");
  const assetsDir = path.join(boardDir, "assets");
  const analysisDir = path.join(boardDir, "analysis");
  const outputDir = path.join(boardDir, "output");
  await Promise.all([rawDir, normalizedDir, assetsDir, analysisDir, outputDir].map((dir) => mkdir(dir, { recursive: true })));

  const bytes = input.backupBytes ?? (input.backupPath ? await readFile(input.backupPath) : null);
  if (!bytes) throw new Error("A backup path or backup bytes are required");
  const backupTarget = path.join(rawDir, "backup.holst");
  if (input.backupPath) await copyFile(input.backupPath, backupTarget);
  else await writeFile(backupTarget, bytes);

  const archive = isHolstArchive(bytes)
    ? await readHolstArchive({ bytes, assetsDir, extractAssets: input.downloadAssets !== false })
    : null;
  const decoded = archive
    ? {
        encodingVersion: 2 as const,
        rootNames: ["objects"],
        objects: archive.data.objects.map((value, index) => ({
          key: typeof value.id === "string" ? value.id : `object-${index + 1}`,
          value,
        })),
        documents: {},
      }
    : decodeHolstBackup(bytes, input.preferredEncodingVersion);
  const normalized = normalizeBoard({
    boardId: input.boardId,
    decoded,
    source: {
      ...input.source,
      format: archive ? "holst-archive" : "yjs-update",
      boardName: archive?.data.boardName ?? input.source.boardName,
      encodingVersion: archive ? undefined : decoded.encodingVersion,
    },
    observedAssetUrls: input.observedAssetUrls,
  });
  const normalizedPath = path.join(normalizedDir, "board.json");
  await writeFile(normalizedPath, `${JSON.stringify(normalized, null, 2)}\n`);

  let manifest: Awaited<ReturnType<typeof downloadBoardAssets>> = archive?.assets ?? [];
  if (!archive && input.downloadAssets !== false) {
    manifest = await downloadBoardAssets(normalized.assetUrls, assetsDir);
  }
  await writeFile(path.join(assetsDir, "manifest.json"), `${JSON.stringify(manifest, null, 2)}\n`);

  const assetFilename = (urlString: string) => {
    if (urlString.startsWith("archive:///")) return path.basename(urlString.slice("archive:///".length));
    try {
      return path.basename(new URL(urlString).pathname);
    } catch {
      return "";
    }
  };
  const catalog = createAnalysisCatalog({
    boardId: input.boardId,
    textItems: normalized.objects
      .filter((object): object is typeof object & { text: string } => Boolean(object.text))
      .sort(
        (left, right) =>
          (left.frameId ?? "").localeCompare(right.frameId ?? "") ||
          (left.position.y ?? 0) - (right.position.y ?? 0) ||
          (left.position.x ?? 0) - (right.position.x ?? 0),
      )
      .map((object) => ({
        objectId: object.id,
        frameId: object.frameId,
        objectType: object.type,
        text: object.text,
      })),
    assetItems: manifest
      .filter(
        (item): item is typeof item & { localPath: string } => item.status === "downloaded" && Boolean(item.localPath),
      )
      .map((item, index) => {
        const filename = item.archiveName ?? assetFilename(item.sourceUrl);
        return {
          id: `asset-${String(index + 1).padStart(4, "0")}`,
          assetPath: item.localPath,
          sha256: item.sha256,
          sourceUrl: item.sourceUrl,
          contentType: item.contentType,
          kind: item.contentType?.startsWith("audio/") ? ("audio" as const) : ("image" as const),
          relatedObjectIds: normalized.objects
            .filter(
              (object) =>
                object.assetUrls.some((url) => assetFilename(url) === filename) ||
                object.raw.name === filename ||
                object.raw.fileName === filename,
            )
            .map((object) => object.id),
        };
      }),
  });
  const queue = await writeIncrementalAnalysisQueue({
    analysisDir,
    catalog,
    instructions: [
      "Analyze text and educational images as evidence of Greek learning.",
      "Inspect only textItems and assetItems: they contain new or changed content since the last completed analysis.",
      "Do not reopen reusedTextItems or reusedAssetItems; they are reference-only records for content already analyzed.",
      "Identify grammar, vocabulary, language functions, conversation topics, completed work, and corrections.",
      "Ignore avatars, UI graphics, decorative images, and unrelated personal photos.",
      "Board presence supports introduced; only attempted or completed work supports practiced.",
      "Never infer confirmed mastery from board content alone.",
    ],
  });

  const evidencePath = path.join(analysisDir, "evidence.jsonl");
  try {
    await readFile(evidencePath);
  } catch {
    await writeFile(evidencePath, "");
  }
  await buildLearnerProfile(boardDir);

  return {
    boardDir,
    normalizedPath,
    assetsDownloaded: manifest.filter((item) => item.status === "downloaded" && !item.reused).length,
    assetsReused: manifest.filter((item) => item.status === "downloaded" && item.reused).length,
    assetsFailed: manifest.filter((item) => item.status === "failed").length,
    analysis: {
      newOrChangedTextItems: queue.summary.newOrChangedTextItems,
      reusedTextReferences: queue.summary.reusedTextReferences,
      newAssets: queue.summary.newAssets,
      reusedAssetReferences: queue.summary.reusedAssetReferences,
    },
    stats: normalized.stats,
  };
}

export function localBoardId(filename: string, bytes: Uint8Array): string {
  const basename = path.basename(filename, path.extname(filename)).replace(/[^a-z0-9_-]+/gi, "-").replace(/^-|-$/g, "");
  return basename || `local-${createHash("sha256").update(bytes).digest("hex").slice(0, 12)}`;
}
