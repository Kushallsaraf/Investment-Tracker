import type {
  ActivityInput,
  ActivityPayload,
  AIReview,
  Analytics,
  ChartPayload,
  ChartRange,
  ClaudePrompt,
  DecisionName,
  ExitPlan,
  ExitPlanInput,
  ExitPlanStatus,
  Fundamentals,
  HistoryPoint,
  IncomePayload,
  InsiderActivity,
  InvestmentProfile,
  McpSetup,
  NewsPayload,
  Note,
  JournalPayload,
  PeerComparison,
  Portfolio,
  PortfolioStatus,
  PositionInput,
  PriceCapabilities,
  ReviewPack,
  ReviewPrivacy,
  SectorAnalysis,
  SectorName,
  StripItem,
  SymbolJournal,
  Technicals,
  WatchlistItem,
} from "./types";

const WRITE_HEADERS = {
  "Content-Type": "application/json",
  "X-Portfolio-Manager": "local-ui",
};

async function responseJson<T>(response: Response): Promise<T> {
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.detail ?? `Request failed (${response.status})`);
  }
  return payload as T;
}

export async function getPortfolio(): Promise<Portfolio | null> {
  const payload = await responseJson<{ portfolio: Portfolio | null }>(await fetch("/api/portfolio"));
  return payload.portfolio;
}

export async function getHistory(): Promise<HistoryPoint[]> {
  const payload = await responseJson<{ history: HistoryPoint[] }>(await fetch("/api/portfolio/history"));
  return payload.history;
}

export async function getSectorAnalysis(): Promise<SectorAnalysis | null> {
  const payload = await responseJson<{ analysis: SectorAnalysis | null }>(await fetch("/api/portfolio/sectors"));
  return payload.analysis;
}

export async function getAnalytics(): Promise<Analytics> {
  const payload = await responseJson<{ analytics: Analytics }>(await fetch("/api/analytics"));
  return payload.analytics;
}

export async function getActivity(params: {
  activityType?: string;
  symbol?: string;
  startDate?: string;
  endDate?: string;
} = {}): Promise<ActivityPayload> {
  const query = new URLSearchParams();
  if (params.activityType) query.set("activity_type", params.activityType);
  if (params.symbol) query.set("symbol", params.symbol);
  if (params.startDate) query.set("start_date", params.startDate);
  if (params.endDate) query.set("end_date", params.endDate);
  const suffix = query.size ? `?${query}` : "";
  return responseJson<ActivityPayload>(await fetch(`/api/activity${suffix}`));
}

export async function getIncome(): Promise<IncomePayload> {
  const payload = await responseJson<{ income: IncomePayload }>(await fetch("/api/income"));
  return payload.income;
}

export async function getJournal(): Promise<JournalPayload> {
  const payload = await responseJson<{ journal: JournalPayload }>(await fetch("/api/journal"));
  return payload.journal;
}

export async function getPrompts(): Promise<ClaudePrompt[]> {
  const payload = await responseJson<{ prompts: ClaudePrompt[] }>(await fetch("/api/research/prompts"));
  return payload.prompts;
}

export async function getAIReviews(): Promise<AIReview[]> {
  const payload = await responseJson<{ reviews: AIReview[] }>(await fetch("/api/research/reviews"));
  return payload.reviews;
}

export async function getPortfolioStatus(): Promise<PortfolioStatus> {
  return responseJson<PortfolioStatus>(await fetch("/api/portfolio/status"));
}

export async function getPriceCapabilities(): Promise<PriceCapabilities> {
  return responseJson<PriceCapabilities>(await fetch("/api/prices/capabilities"));
}

export async function upsertPosition(position: PositionInput): Promise<string> {
  const payload = await responseJson<{ symbol: string }>(await fetch("/api/portfolio/positions", {
    method: "POST",
    headers: WRITE_HEADERS,
    body: JSON.stringify(position),
  }));
  return payload.symbol;
}

export async function loadDemoPortfolio(): Promise<void> {
  await responseJson(await fetch("/api/portfolio/demo", {
    method: "POST",
    headers: WRITE_HEADERS,
    body: JSON.stringify({ confirm: "LOAD DEMO" }),
  }));
}

export async function deletePortfolioData(): Promise<void> {
  await responseJson(await fetch("/api/portfolio/local-data", {
    method: "DELETE",
    headers: WRITE_HEADERS,
    body: JSON.stringify({ confirm: "DELETE LOCAL DATA" }),
  }));
}

export async function createActivity(activity: ActivityInput): Promise<void> {
  await responseJson(await fetch("/api/activity", {
    method: "POST",
    headers: WRITE_HEADERS,
    body: JSON.stringify(activity),
  }));
}

export async function deleteActivity(activityId: string): Promise<void> {
  await responseJson(await fetch(`/api/activity/${activityId}`, {
    method: "DELETE",
    headers: WRITE_HEADERS,
  }));
}

export async function refreshPrices(): Promise<void> {
  await responseJson(await fetch("/api/portfolio/refresh", {
    method: "POST",
    headers: WRITE_HEADERS,
  }));
}

export async function removePortfolioPosition(positionId: string): Promise<void> {
  await responseJson(await fetch(`/api/portfolio/positions/${positionId}`, {
    method: "DELETE",
    headers: WRITE_HEADERS,
  }));
}

export async function updateInstrumentSector(instrumentId: string, sector: SectorName | null): Promise<void> {
  await responseJson(await fetch(`/api/instruments/${instrumentId}/sector`, {
    method: "PUT",
    headers: WRITE_HEADERS,
    body: JSON.stringify({ sector }),
  }));
}

export async function updateDecision(
  instrumentId: string,
  decision: DecisionName,
  reason = "",
  claudeDisposition: "ACCEPTED" | "REJECTED" | "CONSIDERING" | null = null,
  reviewDueDate: string | null = null,
): Promise<void> {
  await responseJson(await fetch(`/api/journal/instruments/${instrumentId}/decisions`, {
    method: "POST",
    headers: WRITE_HEADERS,
    body: JSON.stringify({
      decision,
      decision_date: new Date().toISOString().slice(0, 10),
      reason,
      claude_disposition: claudeDisposition,
      review_due_date: reviewDueDate,
    }),
  }));
}

export async function updateInvestmentProfile(
  instrumentId: string,
  profile: Partial<Omit<InvestmentProfile, "instrument_id" | "symbol" | "updated_at">>,
): Promise<void> {
  await responseJson(await fetch(`/api/journal/instruments/${instrumentId}/profile`, {
    method: "PUT",
    headers: WRITE_HEADERS,
    body: JSON.stringify(profile),
  }));
}

export async function createReviewTrigger(instrumentId: string, trigger: Record<string, unknown>): Promise<void> {
  await responseJson(await fetch(`/api/journal/instruments/${instrumentId}/triggers`, {
    method: "POST",
    headers: WRITE_HEADERS,
    body: JSON.stringify(trigger),
  }));
}

export async function savePrompt(prompt: { id?: string; name: string; prompt_text: string }): Promise<ClaudePrompt> {
  const payload = await responseJson<{ prompt: ClaudePrompt }>(await fetch("/api/research/prompts", {
    method: "PUT",
    headers: WRITE_HEADERS,
    body: JSON.stringify(prompt),
  }));
  return payload.prompt;
}

export async function generateReviewPack(
  instrumentId: string,
  promptId: string,
  triggerId: string | null,
  privacy: ReviewPrivacy,
  save: boolean,
): Promise<ReviewPack> {
  const payload = await responseJson<{ pack: ReviewPack }>(await fetch(
    `/api/research/packs/${save ? "export" : "preview"}`,
    {
      method: "POST",
      headers: WRITE_HEADERS,
      body: JSON.stringify({
        instrument_id: instrumentId,
        prompt_id: promptId,
        trigger_id: triggerId,
        privacy,
      }),
    },
  ));
  return payload.pack;
}

export async function importAIReview(review: Record<string, unknown>): Promise<void> {
  await responseJson(await fetch("/api/research/reviews", {
    method: "POST",
    headers: WRITE_HEADERS,
    body: JSON.stringify(review),
  }));
}

export async function getMarketStrip(): Promise<StripItem[]> {
  const payload = await responseJson<{ items: StripItem[] }>(await fetch("/api/market/strip"));
  return payload.items;
}

export async function getChart(symbol: string, range: ChartRange): Promise<ChartPayload> {
  return responseJson<ChartPayload>(await fetch(`/api/market/${encodeURIComponent(symbol)}/chart?range=${range}`));
}

export async function getTechnicals(symbol: string): Promise<Technicals> {
  return responseJson<Technicals>(await fetch(`/api/market/${encodeURIComponent(symbol)}/technicals`));
}

export async function getWatchlist(): Promise<WatchlistItem[]> {
  const payload = await responseJson<{ items: WatchlistItem[] }>(await fetch("/api/watchlist"));
  return payload.items;
}

export async function addToWatchlist(symbol: string): Promise<void> {
  await responseJson(await fetch("/api/watchlist", {
    method: "POST",
    headers: WRITE_HEADERS,
    body: JSON.stringify({ symbol }),
  }));
}

export async function removeFromWatchlist(symbol: string): Promise<void> {
  await responseJson(await fetch(`/api/watchlist/${encodeURIComponent(symbol)}`, {
    method: "DELETE",
    headers: WRITE_HEADERS,
  }));
}

export async function getFundamentals(symbol: string): Promise<Fundamentals> {
  return responseJson<Fundamentals>(await fetch(`/api/market/${encodeURIComponent(symbol)}/fundamentals`));
}

export async function getInsiderActivity(symbol: string): Promise<InsiderActivity> {
  return responseJson<InsiderActivity>(await fetch(`/api/market/${encodeURIComponent(symbol)}/insiders?days=90`));
}

export async function getPeers(symbol: string): Promise<PeerComparison> {
  return responseJson<PeerComparison>(await fetch(`/api/market/${encodeURIComponent(symbol)}/peers`));
}

export async function savePeers(symbol: string, symbols: string[]): Promise<PeerComparison> {
  return responseJson<PeerComparison>(await fetch(`/api/market/${encodeURIComponent(symbol)}/peers`, {
    method: "PUT",
    headers: WRITE_HEADERS,
    body: JSON.stringify({ symbols }),
  }));
}

export async function resetPeers(symbol: string): Promise<PeerComparison> {
  return responseJson<PeerComparison>(await fetch(`/api/market/${encodeURIComponent(symbol)}/peers`, {
    method: "DELETE",
    headers: WRITE_HEADERS,
  }));
}

export async function getSymbolJournal(symbol: string): Promise<SymbolJournal> {
  return responseJson<SymbolJournal>(await fetch(`/api/market/${encodeURIComponent(symbol)}/journal`));
}

export async function saveSymbolDecision(symbol: string, decision: DecisionName, reason: string): Promise<SymbolJournal> {
  return responseJson<SymbolJournal>(await fetch(`/api/market/${encodeURIComponent(symbol)}/decision`, {
    method: "POST",
    headers: WRITE_HEADERS,
    body: JSON.stringify({ decision, decision_date: new Date().toISOString().slice(0, 10), reason }),
  }));
}

export async function addNote(symbol: string, body: string, pinnedDate: string | null): Promise<Note> {
  const payload = await responseJson<{ note: Note }>(await fetch(`/api/market/${encodeURIComponent(symbol)}/notes`, {
    method: "POST",
    headers: WRITE_HEADERS,
    body: JSON.stringify({ body, pinned_date: pinnedDate }),
  }));
  return payload.note;
}

export async function updateNote(noteId: string, body: string, pinnedDate: string | null): Promise<Note> {
  const payload = await responseJson<{ note: Note }>(await fetch(`/api/notes/${noteId}`, {
    method: "PUT",
    headers: WRITE_HEADERS,
    body: JSON.stringify({ body, pinned_date: pinnedDate }),
  }));
  return payload.note;
}

export async function deleteNote(noteId: string): Promise<void> {
  await responseJson(await fetch(`/api/notes/${noteId}`, { method: "DELETE", headers: WRITE_HEADERS }));
}

export async function getExitPlans(status?: ExitPlanStatus): Promise<ExitPlan[]> {
  const query = status ? `?status=${status}` : "";
  return (await responseJson<{ plans: ExitPlan[] }>(await fetch(`/api/exit-plans${query}`))).plans;
}

export async function createExitPlan(symbol: string, plan: ExitPlanInput): Promise<ExitPlan> {
  const payload = await responseJson<{ plan: ExitPlan }>(await fetch(`/api/market/${encodeURIComponent(symbol)}/exit-plans`, {
    method: "POST",
    headers: WRITE_HEADERS,
    body: JSON.stringify(plan),
  }));
  return payload.plan;
}

export async function decideExitPlan(planId: string, decision: "accept" | "reject"): Promise<ExitPlan> {
  const payload = await responseJson<{ plan: ExitPlan }>(await fetch(`/api/exit-plans/${planId}/${decision}`, {
    method: "POST",
    headers: WRITE_HEADERS,
  }));
  return payload.plan;
}

export async function getMcpSetup(): Promise<McpSetup> {
  return responseJson<McpSetup>(await fetch("/api/mcp/setup"));
}

export async function getNews(symbol: string): Promise<NewsPayload> {
  return responseJson<NewsPayload>(await fetch(`/api/market/${encodeURIComponent(symbol)}/news`));
}
