import assert from "node:assert/strict";
import test from "node:test";
import { renderChatGptUpdate, type LearnerProfileSnapshot } from "../src/profile/chatgpt-update.js";

const baseline: LearnerProfileSnapshot = {
  schemaVersion: 1,
  generatedAt: "2026-08-09T00:00:00.000Z",
  boardId: "board-1",
  status: "ready_for_calibration",
  proficiencyEstimate: { label: "A0 — начало A1" },
  skills: [
    {
      skillId: "grammar.eimai",
      label: "Настоящее время είμαι",
      category: "grammar",
      status: "introduced",
      confidence: 0.8,
      evidence: [
        {
          source: { objectId: "old-object" },
          evidenceType: "lesson_material",
          observation: "Формы появились в учебном материале.",
        },
      ],
    },
  ],
};

test("renders a cumulative ChatGPT update from a fixed baseline", () => {
  const current: LearnerProfileSnapshot = {
    ...baseline,
    generatedAt: "2026-08-10T00:00:00.000Z",
    skills: [
      {
        ...baseline.skills[0],
        status: "practiced",
        evidence: [
          ...baseline.skills[0].evidence,
          {
            source: { objectId: "homework-object" },
            evidenceType: "completed_exercise",
            observation: "Упражнение на формы είμαι заполнено.",
          },
        ],
      },
      {
        skillId: "grammar.meno",
        label: "Настоящее время μένω",
        category: "grammar",
        status: "introduced",
        confidence: 0.9,
        evidence: [
          {
            source: { objectId: "new-object" },
            evidenceType: "lesson_material",
            observation: "Добавлена таблица спряжения μένω.",
          },
        ],
      },
    ],
  };

  const update = renderChatGptUpdate(baseline, current);
  assert.match(update, /Настоящее время μένω/);
  assert.match(update, /`introduced` → `practiced`/);
  assert.match(update, /Упражнение на формы είμαι заполнено/);
  assert.doesNotMatch(update, /Формы появились в учебном материале/);
});
