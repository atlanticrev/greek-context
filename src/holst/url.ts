const BOARD_ID_PATTERN = /^[0-9a-f-]{20,}$/i;

export function parseBoardUrl(input: string): { boardId: string; url: string; origin: string } {
  let url: URL;
  try {
    url = new URL(input);
  } catch {
    throw new Error(`Invalid Holst board URL: ${input}`);
  }

  if (url.protocol !== "https:" || url.hostname !== "app.holst.so") {
    throw new Error("Board URL must use https://app.holst.so");
  }

  const match = url.pathname.match(/^\/board\/([^/]+)/);
  const boardId = match?.[1];
  if (!boardId || !BOARD_ID_PATTERN.test(boardId)) {
    throw new Error("Could not find a valid board ID in the Holst URL");
  }

  return {
    boardId,
    url: `https://app.holst.so/board/${boardId}`,
    origin: url.origin,
  };
}
