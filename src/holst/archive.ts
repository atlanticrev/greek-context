import { createHash } from "node:crypto";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import unzipper from "unzipper";
import type { JsonValue } from "../types.js";
import type { AssetManifestEntry } from "./assets.js";

export interface HolstArchiveData {
  boardName?: string;
  version?: number;
  objects: Array<Record<string, JsonValue>>;
  comments?: JsonValue[];
  backgroundColor?: JsonValue;
}

const MIME_TYPES: Record<string, string> = {
  ".avif": "image/avif",
  ".gif": "image/gif",
  ".jpeg": "image/jpeg",
  ".jpg": "image/jpeg",
  ".mp3": "audio/mpeg",
  ".ogg": "audio/ogg",
  ".png": "image/png",
  ".svg": "image/svg+xml",
  ".wav": "audio/wav",
  ".webm": "audio/webm",
  ".webp": "image/webp",
};

function parseArchiveData(bytes: Buffer): HolstArchiveData {
  let value: unknown;
  try {
    value = JSON.parse(bytes.toString("utf8"));
  } catch (error) {
    throw new Error(`Invalid data.json in Holst archive: ${error instanceof Error ? error.message : String(error)}`);
  }
  if (!value || typeof value !== "object" || !Array.isArray((value as { objects?: unknown }).objects)) {
    throw new Error("Holst archive data.json does not contain an objects array");
  }
  return value as HolstArchiveData;
}

export function isHolstArchive(bytes: Uint8Array): boolean {
  return bytes.length >= 4 && bytes[0] === 0x50 && bytes[1] === 0x4b;
}

export async function readHolstArchive(input: {
  bytes: Uint8Array;
  assetsDir: string;
  extractAssets: boolean;
}): Promise<{ data: HolstArchiveData; assets: AssetManifestEntry[] }> {
  const directory = await unzipper.Open.buffer(Buffer.from(input.bytes));
  const dataEntry = directory.files.find((entry) => entry.path === "data.json");
  if (!dataEntry) throw new Error("Holst archive does not contain data.json");
  const data = parseArchiveData(await dataEntry.buffer());
  if (!input.extractAssets) return { data, assets: [] };

  const filesDir = path.join(input.assetsDir, "files");
  await mkdir(filesDir, { recursive: true });
  const assets: AssetManifestEntry[] = [];

  for (const entry of directory.files) {
    if (entry.type === "Directory" || entry.path === "data.json") continue;
    const archiveName = path.basename(entry.path);
    const extension = path.extname(archiveName).toLowerCase();
    const contentType = MIME_TYPES[extension];
    if (!contentType) continue;

    try {
      const fileBytes = await entry.buffer();
      const sha256 = createHash("sha256").update(fileBytes).digest("hex");
      const safeFilename = archiveName.replace(/[^a-z0-9._-]+/gi, "-");
      const absolutePath = path.join(filesDir, safeFilename);
      let reused = false;
      try {
        const existingBytes = await readFile(absolutePath);
        reused =
          existingBytes.length === fileBytes.length &&
          createHash("sha256").update(existingBytes).digest("hex") === sha256;
      } catch {
        // Missing or unreadable files are replaced from the trusted local backup.
      }
      if (!reused) await writeFile(absolutePath, fileBytes);
      assets.push({
        sourceUrl: `archive:///${archiveName}`,
        archiveName,
        resolvedUrl: null,
        status: "downloaded",
        localPath: path.posix.join("assets", "files", safeFilename),
        contentType,
        byteLength: fileBytes.length,
        sha256,
        reused,
      });
    } catch (error) {
      assets.push({
        sourceUrl: `archive:///${archiveName}`,
        archiveName,
        resolvedUrl: null,
        status: "failed",
        localPath: null,
        contentType,
        byteLength: null,
        sha256: null,
        error: error instanceof Error ? error.message : String(error),
      });
    }
  }

  return { data, assets };
}
