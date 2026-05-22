const BASE = "/api";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(BASE + path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `HTTP ${res.status}`);
  }
  return res.json();
}

// --- Scraping ---
export const scrapeApi = {
  byDate: (date: string) =>
    request<{ race_ids: string[] }>(`/scrape/by-date?date=${date}`),

  scrapeRace: (race_id: string) =>
    request<{ success: boolean; race_name?: string; location?: string }>(
      "/scrape/race",
      { method: "POST", body: JSON.stringify({ race_id }) }
    ),

  upcoming: (date: string) =>
    request<{ race_ids: string[] }>(`/scrape/upcoming?date=${date}`),

  shutuba: (race_id: string) =>
    request<Record<string, unknown>>(`/scrape/shutuba/${race_id}`),
};

// --- Model ---
export const modelApi = {
  status: () =>
    request<{ trained: boolean; mode?: string; jockeys?: number; horses?: number }>(
      "/model/status"
    ),

  startTraining: (mode: string) =>
    request<{ task_id: string }>(`/model/train/start?mode=${mode}`, {
      method: "POST",
    }),

  rankings: () =>
    request<{
      jockeys: { name: string; score: number; std?: number }[];
      horses: { name: string; score: number; std?: number }[];
      mode: string;
    }>("/model/rankings"),

  predict: (entries: { jockey: string; horse: string }[]) =>
    request<
      { jockey: string; horse: string; win_pct: number; top3_pct: number; status: string }[]
    >("/model/predict", { method: "POST", body: JSON.stringify(entries) }),
};

// --- Database ---
export const dbApi = {
  stats: () =>
    request<{ races: number; horses: number; entries: number; results: number }>(
      "/db/stats"
    ),

  getTable: (table: string) =>
    request<Record<string, unknown>[]>(`/db/${table}`),

  deleteRace: (race_id: string) =>
    request<{ success: boolean }>(`/db/race/${race_id}`, { method: "DELETE" }),

  exportUrl: (table: string) => `${BASE}/db/${table}/export`,

  resetDb: () =>
    request<{ success: boolean }>("/db/reset", { method: "DELETE" }),
};
