import { readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { z } from "zod";
import type { LearningCategory, LearningEvidence, LearningStatus, NormalizedBoard } from "../types.js";
import { writeChatGptUpdate, type LearnerProfileSnapshot } from "./chatgpt-update.js";

const evidenceSchema = z.object({
  skillId: z.string().min(1),
  label: z.string().min(1),
  category: z.enum(["grammar", "vocabulary", "conversation_topic", "language_function", "pronunciation"]),
  status: z.enum(["introduced", "practiced", "needs_review", "confirmed", "no_evidence"]),
  confidence: z.number().min(0).max(1),
  source: z.object({
    objectId: z.string().optional(),
    assetPath: z.string().optional(),
    frameId: z.string().optional(),
  }),
  evidenceType: z.string().min(1),
  observation: z.string().min(1),
});

const STATUS_RANK: Record<LearningStatus, number> = {
  no_evidence: 0,
  introduced: 1,
  needs_review: 2,
  practiced: 3,
  confirmed: 4,
};

async function readEvidence(filename: string): Promise<LearningEvidence[]> {
  try {
    const contents = await readFile(filename, "utf8");
    return contents
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter(Boolean)
      .map((line, index) => {
        try {
          return evidenceSchema.parse(JSON.parse(line));
        } catch (error) {
          throw new Error(`Invalid evidence at line ${index + 1}: ${error instanceof Error ? error.message : String(error)}`);
        }
      });
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") return [];
    throw error;
  }
}

export async function buildLearnerProfile(
  boardDir: string,
): Promise<{ profilePath: string; contextPath: string; instructionsPath: string; updatePath: string | null }> {
  const board = JSON.parse(await readFile(path.join(boardDir, "normalized", "board.json"), "utf8")) as NormalizedBoard;
  const evidence = await readEvidence(path.join(boardDir, "analysis", "evidence.jsonl"));
  const grouped = new Map<string, LearningEvidence[]>();
  for (const item of evidence) grouped.set(item.skillId, [...(grouped.get(item.skillId) ?? []), item]);

  const skills = [...grouped.entries()]
    .map(([skillId, items]) => {
      const strongest = [...items].sort(
        (left, right) => STATUS_RANK[right.status] - STATUS_RANK[left.status] || right.confidence - left.confidence,
      )[0];
      return {
        skillId,
        label: strongest.label,
        category: strongest.category,
        status: strongest.status,
        confidence: Math.max(...items.map((item) => item.confidence)),
        evidence: items.map((item) => ({
          source: item.source,
          evidenceType: item.evidenceType,
          observation: item.observation,
        })),
      };
    })
    .sort((left, right) => left.category.localeCompare(right.category) || left.label.localeCompare(right.label));

  const profile = {
    schemaVersion: 1,
    generatedAt: new Date().toISOString(),
    boardId: board.boardId,
    sourceSummary: board.stats,
    status: skills.length === 0 ? "awaiting_analysis" : "ready_for_calibration",
    proficiencyEstimate: skills.length === 0 ? null : {
      label: "A0 — начало A1",
      kind: "conservative_board_based_estimate",
      note: "Это оценка диапазона материалов, а не результат языкового теста.",
    },
    rules: {
      boardPresenceDoesNotMeanMastery: true,
      confirmedRequiresAssessment: true,
      noEvidenceDoesNotMeanUnknown: true,
    },
    skills,
  };

  const labels = (category: LearningCategory, statuses: LearningStatus[]) =>
    skills.filter((skill) => skill.category === category && statuses.includes(skill.status)).map((skill) => skill.label);
  const safeTopics = labels("conversation_topic", ["practiced", "confirmed"]);
  const stretchTopics = labels("conversation_topic", ["introduced", "needs_review"]);
  const safeGrammar = labels("grammar", ["practiced", "confirmed"]);
  const reviewGrammar = labels("grammar", ["introduced", "needs_review"]);
  const safeFunctions = labels("language_function", ["practiced", "confirmed"]);
  const stretchFunctions = labels("language_function", ["introduced", "needs_review"]);
  const safeVocabulary = labels("vocabulary", ["practiced", "confirmed"]);
  const stretchVocabulary = labels("vocabulary", ["introduced", "needs_review"]);
  const safePronunciation = labels("pronunciation", ["practiced", "confirmed"]);
  const stretchPronunciation = labels("pronunciation", ["introduced", "needs_review"]);
  const hasConfirmedSkill = skills.some((skill) => skill.status === "confirmed");
  const bullets = (items: string[], fallback: string) => items.length ? items.map((item) => `- ${item}`) : [`- ${fallback}`];

  const context = [
    "# Учебный контекст по греческому",
    "",
    `Источник: доска Holst ${board.boardId}. Рабочий диапазон: A0 — начало A1.`,
    "Это профиль по учебным следам, а не результат теста. Ни один навык пока не подтверждён отдельной проверкой.",
    "",
    "## Как ChatGPT должен вести разговор",
    "",
    "- Веди простой живой диалог на греческом; объяснения и подсказки при необходимости давай по-русски.",
    "- Примерно 80% реплик строй на практиковавшемся материале, до 20% — мягкое расширение.",
    "- Задавай один короткий вопрос за раз. Новую конструкцию сначала покажи на одном примере.",
    "- Исправляй не больше одной-двух важных ошибок за реплику: короткая поправка, затем продолжение разговора.",
    "- Не требуй свободного владения прошедшим или будущим временем: они встречались в текстах, но активное владение не доказано.",
    "- Если навык отсутствует в профиле, это означает «нет свидетельств», а не «ученик этого не знает».",
    "",
    "## Можно уверенно брать для разговора с опорами",
    "",
    ...bullets(safeTopics, "Пока не определено: требуется анализ материалов."),
    "",
    "## Отработанные коммуникативные действия",
    "",
    ...bullets(safeFunctions, "Пока не определены."),
    "",
    "## Грамматика, которую можно использовать",
    "",
    ...bullets(safeGrammar, "Пока не определена."),
    "",
    "## Активный словарь и произношение",
    "",
    ...bullets(safeVocabulary, "Активные словарные темы пока не определены."),
    ...bullets(safePronunciation, "Практика произношения пока не определена."),
    "",
    "## Только знакомый материал: вводить осторожно",
    "",
    ...bullets(
      [...stretchTopics, ...stretchFunctions, ...reviewGrammar, ...stretchVocabulary, ...stretchPronunciation],
      "Пока не определён.",
    ),
    "",
    "## Граница достоверности",
    "",
    hasConfirmedSkill
      ? "- Подтверждённые навыки перечислены в learner-profile.json; остальные требуют калибровки в диалоге."
      : "- Подтверждённых отдельной проверкой навыков пока нет. В начале диалога мягко откалибруй уровень на знакомых темах.",
    "- Длинные учебные тексты показывают знакомство с темой, но не доказывают, что ученик сам строит такие фразы.",
    "- Не повышай уровень автоматически после одного правильного ответа: ищи устойчивость в нескольких репликах.",
    "",
  ].join("\n");

  const instructions = [
    "# Инструкции для ChatGPT Project",
    "",
    "Используй файл `chat-context.md` как границы текущего греческого ученика, а `learner-profile.json` — как подробный источник статусов и доказательств.",
    "Если в Sources есть `chat-context-update.md`, применяй его после базовых файлов: он содержит накопительные изменения и имеет приоритет при конфликте.",
    "",
    "Твоя роль — дружелюбный собеседник и преподаватель новогреческого. Начинай с материала со статусом `practiced` или `confirmed`. Материал `introduced` и `needs_review` добавляй только с короткой подсказкой. Не превращай наличие текста на учебной доске в утверждение об освоении.",
    "",
    "В каждом ходе:",
    "",
    "1. Дай одну короткую естественную реплику по-гречески.",
    "2. Задай один вопрос.",
    "3. При ошибке сначала покажи исправленный вариант, затем продолжи диалог.",
    "4. Если ответ даётся легко несколько раз подряд, понемногу усложняй; если тяжело — вернись к знакомой модели и дай пример.",
    "",
    "По умолчанию держись диапазона A0 — начало A1, используй настоящее время и короткие предложения. Русский применяй для кратких объяснений, но сам разговор старайся сохранять на греческом.",
    "",
  ].join("\n");

  const outputDir = path.join(boardDir, "output");
  await writeFile(path.join(outputDir, "learner-profile.json"), `${JSON.stringify(profile, null, 2)}\n`);
  await writeFile(path.join(outputDir, "chat-context.md"), context);
  await writeFile(path.join(outputDir, "chatgpt-project-instructions.md"), instructions);
  const updatePath = await writeChatGptUpdate(boardDir, profile as LearnerProfileSnapshot);
  return {
    profilePath: path.join(outputDir, "learner-profile.json"),
    contextPath: path.join(outputDir, "chat-context.md"),
    instructionsPath: path.join(outputDir, "chatgpt-project-instructions.md"),
    updatePath,
  };
}
