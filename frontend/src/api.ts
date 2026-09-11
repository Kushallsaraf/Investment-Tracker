import type {
  HistoryPoint,
  Portfolio,
  PriceCapabilities,
  SectorAnalysis,
  SectorName,
  SnapTradeStatus,
  SnapTradeSyncPreview,
} from "./types";

const WRITE_HEADERS = { "X-Portfolio-Manager": "local-ui" };

async function responseJson<T>(response: Response): Promise<T> {
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.detail ?? `Request failed (${response.status})`);
  }
  return payload as T;
}

export async function getPortfolio(): Promise<Portfolio | null> {
  const response = await fetch("/api/portfolio");
  const payload = await responseJson<{ portfolio: Portfolio | null }>(response);
  return payload.portfolio;
}

export async function getHistory(): Promise<HistoryPoint[]> {
  const response = await fetch("/api/portfolio/history");
  const payload = await responseJson<{ history: HistoryPoint[] }>(response);
  return payload.history;
}

export async function getSectorAnalysis(): Promise<SectorAnalysis | null> {
  const response = await fetch("/api/portfolio/sectors");
  const payload = await responseJson<{ analysis: SectorAnalysis | null }>(response);
  return payload.analysis;
}

export async function getSnapTradeStatus(): Promise<SnapTradeStatus> {
  const response = await fetch("/api/snaptrade/status");
  return responseJson<SnapTradeStatus>(response);
}

export async function checkSnapTradeConnection(): Promise<SnapTradeStatus> {
  const response = await fetch("/api/snaptrade/connection/check", {
    method: "POST",
    headers: WRITE_HEADERS,
  });
  return responseJson<SnapTradeStatus>(response);
}

export async function getPriceCapabilities(): Promise<PriceCapabilities> {
  const response = await fetch("/api/prices/capabilities");
  return responseJson<PriceCapabilities>(response);
}

export async function createSnapTradePortal(): Promise<string> {
  const response = await fetch("/api/snaptrade/portal", {
    method: "POST",
    headers: WRITE_HEADERS,
  });
  const payload = await responseJson<{ redirect_uri: string }>(response);
  return payload.redirect_uri;
}

export async function previewSnapTradeSync(): Promise<SnapTradeSyncPreview> {
  const response = await fetch("/api/snaptrade/sync/preview", {
    method: "POST",
    headers: WRITE_HEADERS,
  });
  return responseJson<SnapTradeSyncPreview>(response);
}

export async function getPendingSnapTradeSync(): Promise<SnapTradeSyncPreview | null> {
  const response = await fetch("/api/snaptrade/sync/pending");
  const payload = await responseJson<{ preview: SnapTradeSyncPreview | null }>(response);
  return payload.preview;
}

export async function applySnapTradeSync(previewId: string): Promise<void> {
  const response = await fetch(`/api/snaptrade/sync/${previewId}/apply`, {
    method: "POST",
    headers: { ...WRITE_HEADERS, "Content-Type": "application/json" },
    body: JSON.stringify({ confirm: "APPLY" }),
  });
  await responseJson(response);
}

export async function cancelSnapTradeSync(previewId: string): Promise<void> {
  const response = await fetch(`/api/snaptrade/sync/${previewId}`, {
    method: "DELETE",
    headers: WRITE_HEADERS,
  });
  await responseJson(response);
}

export async function disconnectSnapTrade(): Promise<void> {
  const response = await fetch("/api/snaptrade/disconnect", {
    method: "POST",
    headers: { ...WRITE_HEADERS, "Content-Type": "application/json" },
    body: JSON.stringify({ confirm: "DISCONNECT" }),
  });
  await responseJson(response);
}

export async function deleteLocalBrokerageData(): Promise<void> {
  const response = await fetch("/api/snaptrade/local-data", {
    method: "DELETE",
    headers: { ...WRITE_HEADERS, "Content-Type": "application/json" },
    body: JSON.stringify({ confirm: "DELETE LOCAL DATA" }),
  });
  await responseJson(response);
}

export async function refreshPrices(): Promise<void> {
  const response = await fetch("/api/portfolio/refresh", {
    method: "POST",
    headers: WRITE_HEADERS,
  });
  await responseJson(response);
}

export async function removePortfolioPosition(positionId: string): Promise<void> {
  const response = await fetch(`/api/portfolio/positions/${positionId}`, {
    method: "DELETE",
    headers: WRITE_HEADERS,
  });
  await responseJson(response);
}

export async function updateInstrumentSector(
  instrumentId: string,
  sector: SectorName | null,
): Promise<void> {
  const response = await fetch(`/api/instruments/${instrumentId}/sector`, {
    method: "PUT",
    headers: { ...WRITE_HEADERS, "Content-Type": "application/json" },
    body: JSON.stringify({ sector }),
  });
  await responseJson(response);
}
