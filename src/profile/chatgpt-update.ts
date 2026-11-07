import { readFile, writeFile } from "node:fs/promises";
import path from "node:path";

export interface ProfileEvidence {
  source: {
    objectId?: string;
    assetPath?: string;
    frameId?: string;
  };
  evidenceType: string;
  observation: string;
}

export interface ProfileSkill {
  skillId: string;
  label: string;
  category: "grammar" | "vocabulary" | "conversation_topic" | "language_function" | "pronunciation";
  status: "introduced" | "practiced" | "needs_review" | "confirmed" | "no_evidence";
  confidence: number;
  evidence: ProfileEvidence[];
}

export interface LearnerProfileSnapshot {
  schemaVersion: number;
  generatedAt: string;
  boardId: string;
  status: string;
  proficiencyEstimate: { label: string } | null;
  skills: ProfileSkill[];
}

const BASELINE_FILENAME = "chatgpt-baseline-profile.json";
const UPDATE_FILENAME = "chat-context-update.md";

function evidenceKey(evidence: ProfileEvidence): string {
  return JSON.stringify(evidence);
}

function sourceLabel(evidence: ProfileEvidence): string {
  const parts = [
    evidence.source.frameId ? `frame ${evidence.source.frameId}` : null,
    evidence.source.objectId ? `object ${evidence.source.objectId}` : null,
    evidence.source.assetPath ?? null,
  ].filter(Boolean);
  return parts.length > 0 ? parts.join(", ") : "источник в профиле";
}

function evidenceLines(evidence: ProfileEvidence[], indent = "  "): string[] {
  return evidence.flatMap((item) => [
    `${indent}- ${item.observation}`,
    `${indent}  Источник: ${sourceLabel(item)}; тип: ${item.evidenceType}.`,
  ]);
}

export function renderChatGptUpdate(
  baseline: LearnerProfileSnapshot,
  current: LearnerProfileSnapshot,
): string {
  const baselineById = new Map(baseline.skills.map((skill) => [skill.skillId, skill]));
  const currentById = new Map(current.skills.map((skill) => [skill.skillId, skill]));
  const added = current.skills.filter((skill) => !baselineById.has(skill.skillId));
  const removed = baseline.skills.filter((skill) => !currentById.has(skill.skillId));
  const statusChanges = current.skills
    .map((skill) => ({ before: baselineById.get(skill.skillId), after: skill }))
    .filter(
      (pair): pair is { before: ProfileSkill; after: ProfileSkill } =>
        Boolean(pair.before) &&
        (pair.before?.status !== pair.after.status ||
          pair.before?.label !== pair.after.label ||
          pair.before?.category !== pair.after.category),
    );
  const addedIds = new Set(added.map((skill) => skill.skillId));
  const newEvidence = current.skills
    .filter((skill) => !addedIds.has(skill.skillId) && baselineById.has(skill.skillId))
    .map((skill) => {
      const previousEvidence = new Set((baselineById.get(skill.skillId)?.evidence ?? []).map(evidenceKey));
      return {
        skill,
        evidence: skill.evidence.filter((item) => !previousEvidence.has(evidenceKey(item))),
      };
    })
    .filter((item) => item.evidence.length > 0);

  const lines = [
    "# Накопительное обновление учебного контекста",
    "",
    `Базовый профиль: ${baseline.generatedAt}. Текущий профиль: ${current.generatedAt}.`,
    "Этот файл содержит все изменения после базового снимка. Он дополняет `chat-context.md` и `learner-profile.json`.",
    "Если сведения конфликтуют, используй этот файл как более новый источник.",
    "",
  ];

  if (added.length === 0 && statusChanges.length === 0 && newEvidence.length === 0 && removed.length === 0) {
    lines.push("## Изменения", "", "После базового снимка изменений пока нет.", "");
  }

  if (added.length > 0) {
    lines.push("## Новые навыки и темы", "");
    for (const skill of added) {
      lines.push(`- **${skill.label}** — \`${skill.status}\`, категория \`${skill.category}\`.`);
      lines.push(...evidenceLines(skill.evidence));
    }
    lines.push("");
  }

  if (statusChanges.length > 0) {
    lines.push("## Изменения статуса", "");
    for (const { before, after } of statusChanges) {
      lines.push(`- **${after.label}**: \`${before.status}\` → \`${after.status}\`.`);
    }
    lines.push("");
  }

  if (newEvidence.length > 0) {
    lines.push("## Новые свидетельства по уже известным навыкам", "");
    for (const item of newEvidence) {
      lines.push(`- **${item.skill.label}** — текущий статус \`${item.skill.status}\`.`);
      lines.push(...evidenceLines(item.evidence));
    }
    lines.push("");
  }

  if (removed.length > 0) {
    lines.push("## Больше не поддерживается текущими данными", "");
    for (const skill of removed) lines.push(`- **${skill.label}** — не считать незнанием; свидетельство исчезло из текущего профиля.`);
    lines.push("");
  }

  lines.push(
    "## Правила применения",
    "",
    "- `introduced` означает знакомство с материалом, а не освоение.",
    "- `practiced` означает наличие попытки или выполненного упражнения.",
    "- `confirmed` допустим только после отдельной диагностики или разговорной проверки.",
    "- Отсутствие навыка означает отсутствие свидетельств, а не незнание.",
    "",
  );
  return lines.join("\n");
}

async function readProfile(filename: string): Promise<LearnerProfileSnapshot> {
  return JSON.parse(await readFile(filename, "utf8")) as LearnerProfileSnapshot;
}

export async function writeChatGptUpdate(
  boardDir: string,
  current: LearnerProfileSnapshot,
): Promise<string | null> {
  const baselinePath = path.join(boardDir, "analysis", BASELINE_FILENAME);
  try {
    const baseline = await readProfile(baselinePath);
    const updatePath = path.join(boardDir, "output", UPDATE_FILENAME);
    await writeFile(updatePath, renderChatGptUpdate(baseline, current));
    return updatePath;
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") return null;
    throw error;
  }
}

export async function initializeChatGptBaseline(boardDir: string): Promise<{
  baselinePath: string;
  updatePath: string;
}> {
  const profilePath = path.join(boardDir, "output", "learner-profile.json");
  const profile = await readProfile(profilePath);
  const baselinePath = path.join(boardDir, "analysis", BASELINE_FILENAME);
  await writeFile(baselinePath, `${JSON.stringify(profile, null, 2)}\n`);
  const updatePath = path.join(boardDir, "output", UPDATE_FILENAME);
  await writeFile(updatePath, renderChatGptUpdate(profile, profile));
  return { baselinePath, updatePath };
}
