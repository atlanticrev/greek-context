#!/usr/bin/env node
import { readFile, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { Command } from "commander";
import { markCurrentCatalogAnalyzed } from "./analysis/incremental-queue.js";
import { authenticateHolst, syncHolstBoard } from "./holst/browser-sync.js";
import { findLatestHolstDownload } from "./holst/downloads.js";
import { importBackup, localBoardId } from "./pipeline.js";
import { buildLearnerProfile } from "./profile/build-profile.js";
import { initializeChatGptBaseline } from "./profile/chatgpt-update.js";

const program = new Command();

program
  .name("greek-context")
  .description("Turn a Holst board into structured Greek learning context")
  .version("0.1.0")
  .option("--data-dir <path>", "Private working data directory", "data");

program
  .command("auth")
  .description("Open a dedicated Chrome profile and sign in to Holst")
  .action(async () => {
    const options = program.opts<{ dataDir: string }>();
    const profileDir = path.resolve(options.dataDir, "browser-profile");
    await authenticateHolst(profileDir);
    console.log(`Holst session saved in ${profileDir}`);
  });

program
  .command("sync")
  .description("Download and import the latest Holst backup from a board URL")
  .argument("<board-url>", "Holst board URL")
  .option("--headed", "Show the Chrome window during sync")
  .option("--skip-assets", "Do not download board image assets")
  .action(async (boardUrl: string, commandOptions: { headed?: boolean; skipAssets?: boolean }) => {
    const options = program.opts<{ dataDir: string }>();
    const profileDir = path.resolve(options.dataDir, "browser-profile");
    const synced = await syncHolstBoard({ boardUrl, profileDir, headed: commandOptions.headed });
    const boardDir = path.resolve(options.dataDir, "boards", synced.boardId);
    const result = await importBackup({
      dataDir: options.dataDir,
      boardId: synced.boardId,
      backupBytes: synced.bytes,
      source: {
        kind: "url-sync",
        boardUrl: synced.boardUrl,
        backupDate: synced.backupDate,
        backupKey: synced.backupKey,
        providerType: synced.providerType,
        encodingVersion: synced.providerType === "hud" ? 2 : 1,
      },
      observedAssetUrls: synced.observedAssetUrls,
      downloadAssets: !commandOptions.skipAssets,
      preferredEncodingVersion: synced.providerType === "hud" ? 2 : 1,
    });
    await writeFile(
      path.join(boardDir, "raw", "sync-metadata.json"),
      `${JSON.stringify({ ...synced, bytes: undefined, syncedAt: new Date().toISOString() }, null, 2)}\n`,
    );
    printResult(result);
  });

program
  .command("import")
  .description("Import a manually exported .holst backup")
  .argument("<backup-path>", "Path to .holst backup")
  .option("--board-id <id>", "Stable local board identifier")
  .option("--encoding <version>", "Force Yjs encoding version: 1 or 2")
  .option("--skip-assets", "Do not download discovered image assets")
  .action(async (backupPath: string, commandOptions: { boardId?: string; encoding?: string; skipAssets?: boolean }) => {
    const options = program.opts<{ dataDir: string }>();
    const absoluteBackupPath = path.resolve(backupPath);
    const bytes = await readFile(absoluteBackupPath);
    const boardId = commandOptions.boardId ?? localBoardId(absoluteBackupPath, bytes);
    const encoding = commandOptions.encoding === "1" ? 1 : commandOptions.encoding === "2" ? 2 : undefined;
    if (commandOptions.encoding && !encoding) throw new Error("--encoding must be 1 or 2");
    const result = await importBackup({
      dataDir: options.dataDir,
      boardId,
      backupPath: absoluteBackupPath,
      source: { kind: "backup", encodingVersion: encoding ?? 2 },
      downloadAssets: !commandOptions.skipAssets,
      preferredEncodingVersion: encoding,
    });
    printResult(result);
  });

program
  .command("import-latest")
  .description("Import the newest recent .holst file downloaded by Codex through the user's Chrome")
  .requiredOption("--board-id <id>", "Stable board identifier")
  .option("--downloads-dir <path>", "Chrome downloads directory", path.join(os.homedir(), "Downloads"))
  .option("--name <text>", "Require the downloaded filename to contain this text")
  .option("--max-age-minutes <minutes>", "Ignore older downloads", "15")
  .option("--skip-assets", "Do not extract archive media")
  .action(
    async (commandOptions: {
      boardId: string;
      downloadsDir: string;
      name?: string;
      maxAgeMinutes: string;
      skipAssets?: boolean;
    }) => {
      const options = program.opts<{ dataDir: string }>();
      const maxAgeMinutes = Number(commandOptions.maxAgeMinutes);
      if (!Number.isFinite(maxAgeMinutes) || maxAgeMinutes <= 0) {
        throw new Error("--max-age-minutes must be a positive number");
      }
      const latest = await findLatestHolstDownload({
        downloadsDir: path.resolve(commandOptions.downloadsDir),
        maxAgeMinutes,
        nameIncludes: commandOptions.name,
      });
      console.log(`Using recent Holst download: ${latest}`);
      const result = await importBackup({
        dataDir: options.dataDir,
        boardId: commandOptions.boardId,
        backupPath: latest,
        source: { kind: "backup", format: "holst-archive" },
        downloadAssets: !commandOptions.skipAssets,
      });
      printResult(result);
    },
  );

program
  .command("build-profile")
  .description("Build learner-profile.json and chat-context.md from evidence.jsonl")
  .argument("<board-id>", "Board identifier under data/boards")
  .action(async (boardId: string) => {
    const options = program.opts<{ dataDir: string }>();
    const boardDir = path.resolve(options.dataDir, "boards", boardId);
    const result = await buildLearnerProfile(boardDir);
    const analysisCheckpointPath = await markCurrentCatalogAnalyzed(boardDir);
    console.log(`Profile: ${result.profilePath}`);
    console.log(`Chat context: ${result.contextPath}`);
    console.log(`ChatGPT Project instructions: ${result.instructionsPath}`);
    if (result.updatePath) console.log(`ChatGPT cumulative update: ${result.updatePath}`);
    console.log(`Analysis checkpoint: ${analysisCheckpointPath}`);
  });

program
  .command("init-chatgpt-baseline")
  .description("Use the current learner profile as the baseline for small cumulative ChatGPT Project updates")
  .argument("<board-id>", "Board identifier under data/boards")
  .action(async (boardId: string) => {
    const options = program.opts<{ dataDir: string }>();
    const boardDir = path.resolve(options.dataDir, "boards", boardId);
    await buildLearnerProfile(boardDir);
    const result = await initializeChatGptBaseline(boardDir);
    console.log(`ChatGPT baseline: ${result.baselinePath}`);
    console.log(`ChatGPT cumulative update: ${result.updatePath}`);
  });

function printResult(result: Awaited<ReturnType<typeof importBackup>>): void {
  console.log(`Board directory: ${result.boardDir}`);
  console.log(`Objects: ${result.stats.totalObjects}; frames: ${result.stats.frames}; text objects: ${result.stats.textObjects}`);
  console.log(
    `Asset candidates: ${result.stats.assetCandidates}; extracted: ${result.assetsDownloaded}; reused: ${result.assetsReused}; failed: ${result.assetsFailed}`,
  );
  console.log(
    `Analysis queue: text new/changed ${result.analysis.newOrChangedTextItems}; text references reused ${result.analysis.reusedTextReferences}; assets new ${result.analysis.newAssets}; asset references reused ${result.analysis.reusedAssetReferences}`,
  );
  console.log(`Normalized JSON: ${result.normalizedPath}`);
}

program.parseAsync().catch((error) => {
  console.error(error instanceof Error ? error.message : String(error));
  process.exitCode = 1;
});
