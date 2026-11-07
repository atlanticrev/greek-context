export type JsonValue =
  | null
  | boolean
  | number
  | string
  | JsonValue[]
  | { [key: string]: JsonValue };

export interface DecodedBoard {
  encodingVersion: 1 | 2;
  rootNames: string[];
  objects: Array<{ key: string; value: Record<string, JsonValue> }>;
  documents: Record<string, JsonValue>;
}

export interface NormalizedObject {
  id: string;
  type: string;
  parentId: string | null;
  frameId: string | null;
  text: string | null;
  position: { x: number | null; y: number | null };
  size: { width: number | null; height: number | null };
  assetUrls: string[];
  raw: Record<string, JsonValue>;
}

export interface NormalizedBoard {
  schemaVersion: 1;
  boardId: string;
  generatedAt: string;
  source: {
    kind: "backup" | "url-sync";
    format?: "holst-archive" | "yjs-update";
    boardUrl?: string;
    boardName?: string;
    backupDate?: string;
    backupKey?: string;
    providerType?: string;
    encodingVersion?: 1 | 2;
  };
  stats: {
    totalObjects: number;
    totalDocuments: number;
    byType: Record<string, number>;
    frames: number;
    textObjects: number;
    assetCandidates: number;
  };
  frames: Array<{ id: string; label: string | null; childCount: number }>;
  objects: NormalizedObject[];
  assetUrls: string[];
}

export type LearningCategory =
  | "grammar"
  | "vocabulary"
  | "conversation_topic"
  | "language_function"
  | "pronunciation";

export type LearningStatus =
  | "introduced"
  | "practiced"
  | "needs_review"
  | "confirmed"
  | "no_evidence";

export interface LearningEvidence {
  skillId: string;
  label: string;
  category: LearningCategory;
  status: LearningStatus;
  confidence: number;
  source: {
    objectId?: string;
    assetPath?: string;
    frameId?: string;
  };
  evidenceType: string;
  observation: string;
}
