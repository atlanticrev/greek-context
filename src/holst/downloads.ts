import { readdir, stat } from "node:fs/promises";
import path from "node:path";

export async function findLatestHolstDownload(input: {
  downloadsDir: string;
  maxAgeMinutes?: number;
  nameIncludes?: string;
  now?: number;
}): Promise<string> {
  const now = input.now ?? Date.now();
  const maxAgeMs = (input.maxAgeMinutes ?? 15) * 60_000;
  const nameQuery = input.nameIncludes?.toLocaleLowerCase();
  const entries = await readdir(input.downloadsDir, { withFileTypes: true });
  const candidates = await Promise.all(
    entries
      .filter(
        (entry) =>
          entry.isFile() &&
          entry.name.toLocaleLowerCase().endsWith(".holst") &&
          (!nameQuery || entry.name.toLocaleLowerCase().includes(nameQuery)),
      )
      .map(async (entry) => {
        const filename = path.join(input.downloadsDir, entry.name);
        const metadata = await stat(filename);
        return { filename, mtimeMs: metadata.mtimeMs };
      }),
  );

  const latest = candidates
    .filter((candidate) => now - candidate.mtimeMs <= maxAgeMs)
    .sort((left, right) => right.mtimeMs - left.mtimeMs)[0];

  if (!latest) {
    const nameDescription = input.nameIncludes ? ` containing “${input.nameIncludes}”` : "";
    throw new Error(
      `No .holst download${nameDescription} was found in ${input.downloadsDir} within the last ${input.maxAgeMinutes ?? 15} minutes`,
    );
  }
  return latest.filename;
}
