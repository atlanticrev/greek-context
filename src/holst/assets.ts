import { createHash } from "node:crypto";
import { access, mkdir, writeFile } from "node:fs/promises";
import path from "node:path";

export interface AssetManifestEntry {
  sourceUrl: string;
  archiveName?: string;
  resolvedUrl: string | null;
  status: "downloaded" | "failed" | "skipped";
  localPath: string | null;
  contentType: string | null;
  byteLength: number | null;
  sha256: string | null;
  reused?: boolean;
  error?: string;
}

const MIME_EXTENSIONS: Record<string, string> = {
  "image/avif": ".avif",
  "image/gif": ".gif",
  "image/jpeg": ".jpg",
  "image/png": ".png",
  "image/svg+xml": ".svg",
  "image/webp": ".webp",
};

function sourceCandidate(urlString: string): string {
  const url = new URL(urlString);
  url.pathname = url.pathname.replace(/^\/resize\/(thumbnail|medium|large)\//, "/storage/");
  url.search = "";
  return url.toString();
}

function isBoardAsset(urlString: string): boolean {
  try {
    const url = new URL(urlString);
    return url.hostname === "storage-edge.app.holst.so" && /^\/(storage|resize)\//.test(url.pathname);
  } catch {
    return false;
  }
}

async function downloadOne(urlString: string, filesDir: string): Promise<AssetManifestEntry> {
  if (!isBoardAsset(urlString)) {
    return {
      sourceUrl: urlString,
      resolvedUrl: null,
      status: "skipped",
      localPath: null,
      contentType: null,
      byteLength: null,
      sha256: null,
      error: "Not a Holst storage asset",
    };
  }

  const candidates = [...new Set([sourceCandidate(urlString), urlString])];
  let lastError = "No candidate URL succeeded";

  for (const candidate of candidates) {
    try {
      const response = await fetch(candidate, { redirect: "follow" });
      if (!response.ok) {
        lastError = `${response.status} ${response.statusText}`;
        continue;
      }
      const bytes = Buffer.from(await response.arrayBuffer());
      const contentType = response.headers.get("content-type")?.split(";")[0] ?? "application/octet-stream";
      if (!contentType.startsWith("image/")) {
        lastError = `Unexpected content type: ${contentType}`;
        continue;
      }
      const sha256 = createHash("sha256").update(bytes).digest("hex");
      const extension = MIME_EXTENSIONS[contentType] ?? (path.extname(new URL(candidate).pathname) || ".bin");
      const filename = `${sha256.slice(0, 20)}${extension}`;
      const absolutePath = path.join(filesDir, filename);
      let reused = false;
      try {
        await access(absolutePath);
        reused = true;
      } catch {
        await writeFile(absolutePath, bytes);
      }
      return {
        sourceUrl: urlString,
        resolvedUrl: response.url,
        status: "downloaded",
        localPath: path.posix.join("assets", "files", filename),
        contentType,
        byteLength: bytes.length,
        sha256,
        reused,
      };
    } catch (error) {
      lastError = error instanceof Error ? error.message : String(error);
    }
  }

  return {
    sourceUrl: urlString,
    resolvedUrl: null,
    status: "failed",
    localPath: null,
    contentType: null,
    byteLength: null,
    sha256: null,
    error: lastError,
  };
}

export async function downloadBoardAssets(urls: string[], assetsDir: string): Promise<AssetManifestEntry[]> {
  const filesDir = path.join(assetsDir, "files");
  await mkdir(filesDir, { recursive: true });
  const canonicalAssets = new Map<string, string>();
  for (const url of [...new Set(urls)].filter(isBoardAsset)) {
    const canonical = sourceCandidate(url);
    if (!canonicalAssets.has(canonical)) canonicalAssets.set(canonical, url);
  }
  const uniqueUrls = [...canonicalAssets.values()];
  const results: AssetManifestEntry[] = [];
  const concurrency = 4;

  for (let index = 0; index < uniqueUrls.length; index += concurrency) {
    const batch = uniqueUrls.slice(index, index + concurrency);
    results.push(...(await Promise.all(batch.map((url) => downloadOne(url, filesDir)))));
  }

  const deduplicated = new Map<string, AssetManifestEntry>();
  for (const result of results) {
    const key = result.sha256 ?? result.sourceUrl;
    if (!deduplicated.has(key)) deduplicated.set(key, result);
  }
  return [...deduplicated.values()];
}
