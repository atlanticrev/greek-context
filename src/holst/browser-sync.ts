import { mkdir } from "node:fs/promises";
import path from "node:path";
import { createInterface } from "node:readline/promises";
import { stdin as input, stdout as output } from "node:process";
import { chromium, type BrowserContext } from "playwright-core";
import { parseBoardUrl } from "./url.js";

interface HolstBackupRecord {
  key: string;
  date?: string;
  server_provider_type?: string;
}

export interface SyncedBackup {
  boardId: string;
  boardUrl: string;
  bytes: Buffer;
  backupKey: string;
  backupDate?: string;
  providerType: string;
  observedAssetUrls: string[];
}

async function launchContext(profileDir: string, headless: boolean): Promise<BrowserContext> {
  await mkdir(profileDir, { recursive: true });
  const executablePath = process.env.HOLST_CHROME_EXECUTABLE;
  try {
    return await chromium.launchPersistentContext(profileDir, {
      channel: executablePath ? undefined : "chrome",
      executablePath,
      headless,
      viewport: { width: 1440, height: 1000 },
    });
  } catch (error) {
    throw new Error(
      `Could not launch Google Chrome. Install Chrome or set HOLST_CHROME_EXECUTABLE. ${error instanceof Error ? error.message : String(error)}`,
    );
  }
}

export async function authenticateHolst(profileDir: string): Promise<void> {
  const context = await launchContext(profileDir, false);
  const page = context.pages()[0] ?? (await context.newPage());
  try {
    await page.goto("https://app.holst.so/", { waitUntil: "domcontentloaded" });
    const prompt = createInterface({ input, output });
    await prompt.question("Sign in to Holst in the opened Chrome window, then press Enter here... ");
    prompt.close();

    const response = await context.request.get("https://app.holst.so/gapi/current_user");
    if (!response.ok()) {
      throw new Error(`Holst session check failed with HTTP ${response.status()}`);
    }
  } finally {
    await context.close();
  }
}

function backupRecords(payload: unknown): HolstBackupRecord[] {
  if (Array.isArray(payload)) return payload as HolstBackupRecord[];
  if (payload && typeof payload === "object") {
    const record = payload as Record<string, unknown>;
    if (Array.isArray(record.result)) return record.result as HolstBackupRecord[];
    if (record.data && typeof record.data === "object") {
      const nested = record.data as Record<string, unknown>;
      if (Array.isArray(nested.result)) return nested.result as HolstBackupRecord[];
    }
  }
  return [];
}

export async function syncHolstBoard(input: {
  boardUrl: string;
  profileDir: string;
  headed?: boolean;
}): Promise<SyncedBackup> {
  const board = parseBoardUrl(input.boardUrl);
  const context = await launchContext(input.profileDir, !input.headed);
  try {
    const page = context.pages()[0] ?? (await context.newPage());
    await page.goto(board.url, { waitUntil: "domcontentloaded", timeout: 60_000 });
    await page.waitForTimeout(5_000);

    if (page.url().includes("/login")) {
      throw new Error("Holst authentication is required. Run `greek-context auth` first.");
    }

    const listUrl = `${board.origin}/gapi/backup/list?name=${encodeURIComponent(board.boardId)}`;
    const listResponse = await context.request.get(listUrl, { headers: { referer: board.url } });
    if (listResponse.status() === 401 || listResponse.status() === 403) {
      throw new Error("Holst session has no access to this board. Run `auth` again or import a manual .holst backup.");
    }
    if (!listResponse.ok()) {
      throw new Error(`Holst backup list failed with HTTP ${listResponse.status()}`);
    }

    const records = backupRecords(await listResponse.json());
    const latest = records
      .filter((record) => typeof record.key === "string")
      .sort((left, right) => Date.parse(right.date ?? "") - Date.parse(left.date ?? ""))[0];
    if (!latest) throw new Error("Holst returned no backups for this board");

    const providerType = latest.server_provider_type === "hud" ? "hud" : "hocuspocus";
    const downloadUrl = `${board.origin}/gapi/backup/download?key=${encodeURIComponent(latest.key)}&server_provider_type=${providerType}`;
    const downloadResponse = await context.request.get(downloadUrl, { headers: { referer: board.url } });
    if (!downloadResponse.ok()) {
      throw new Error(`Holst backup download failed with HTTP ${downloadResponse.status()}`);
    }

    const observedAssetUrls = await page.evaluate(() =>
      performance
        .getEntriesByType("resource")
        .map((entry) => entry.name)
        .filter((url) => /https:\/\/storage-edge\.app\.holst\.so\/(storage|resize)\//.test(url)),
    );

    return {
      boardId: board.boardId,
      boardUrl: board.url,
      bytes: Buffer.from(await downloadResponse.body()),
      backupKey: latest.key,
      backupDate: latest.date,
      providerType,
      observedAssetUrls,
    };
  } finally {
    await context.close();
  }
}
