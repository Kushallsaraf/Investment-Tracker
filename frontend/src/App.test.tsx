import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";

describe("App", () => {
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  beforeEach(() => {
    window.localStorage.clear();
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/api/portfolio/history")) {
        return new Response(JSON.stringify({ status: "ok", history: [] }), { status: 200 });
      }
      if (url.includes("/api/portfolio/sectors")) {
        return new Response(JSON.stringify({ status: "empty", analysis: null }), { status: 200 });
      }
      if (url.includes("/api/snaptrade/status")) {
        return new Response(JSON.stringify({
          adapter_enabled: false,
          connection_status: "adapter_disabled",
          connection_permission: null,
          brokerage_name: "Wealthsimple",
          last_checked_at: null,
          last_attempted_sync_at: null,
          last_successful_sync_at: null,
          holdings_as_of: null,
          next_sync_allowed_at: null,
          sync_allowed: false,
          stale: false,
          warnings: [],
        }), { status: 200 });
      }
      if (url.includes("/api/snaptrade/sync/pending")) {
        return new Response(JSON.stringify({ preview: null }), { status: 200 });
      }
      if (url.includes("/api/prices/capabilities")) {
        return new Response(JSON.stringify({
          provider: "Synthetic",
          automatic_refresh_supported: false,
          automatic_refresh_seconds: null,
        }), { status: 200 });
      }
      return new Response(JSON.stringify({ status: "empty", portfolio: null }), { status: 200 });
    }));
  });

  it("shows the disabled-by-default read-only connection starting point", async () => {
    render(<App />);
    expect(await screen.findByText("NO PORTFOLIO LOADED")).toBeInTheDocument();
    expect(screen.getByText("ADAPTER DISABLED")).toBeInTheDocument();
    expect(screen.getByText(/No credentials can be entered in this application/i)).toBeInTheDocument();
    expect(screen.queryByText(/IMPORT CSV/)).not.toBeInTheDocument();
  });

  it("renders the sector pie and spreadsheet sector dropdown", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/api/portfolio/positions/")) {
        return new Response(JSON.stringify({ status: "deleted" }), { status: 200 });
      }
      if (url.includes("/api/portfolio/history")) {
        return new Response(JSON.stringify({ status: "ok", history: [] }), { status: 200 });
      }
      if (url.includes("/api/portfolio/sectors")) {
        return new Response(JSON.stringify({
          status: "ok",
          analysis: {
            valuation_snapshot_id: "value-1",
            calculated_at: "2026-09-09T12:00:00Z",
            total_cad: "100",
            covered_value_cad: "70",
            coverage_pct: "0.7",
            etf_value_cad: "0",
            etf_covered_value_cad: "0",
            etf_coverage_pct: "1",
            categories: [
              { sector: "Industrials", market_value_cad: "70", portfolio_weight: "0.7" },
              { sector: "Unknown", market_value_cad: "30", portfolio_weight: "0.3" },
            ],
            evidence: [],
            warnings: ["ACME.TO needs a sector."],
            sector_options: ["Industrials", "Information Technology"],
          },
        }), { status: 200 });
      }
      if (url.includes("/api/snaptrade/status")) {
        return new Response(JSON.stringify({
          adapter_enabled: true,
          connection_status: "connected_read_only",
          connection_permission: "read",
          brokerage_name: "Wealthsimple",
          last_checked_at: "2026-09-09T12:00:00Z",
          last_attempted_sync_at: "2026-09-09T12:00:00Z",
          last_successful_sync_at: "2026-09-09T12:00:00Z",
          holdings_as_of: "2026-09-09T12:00:00Z",
          next_sync_allowed_at: "2099-09-09T12:10:00Z",
          sync_allowed: false,
          stale: false,
          warnings: [],
        }), { status: 200 });
      }
      if (url.includes("/api/snaptrade/sync/pending")) {
        return new Response(JSON.stringify({ preview: null }), { status: 200 });
      }
      if (url.includes("/api/prices/capabilities")) {
        return new Response(JSON.stringify({
          provider: "Synthetic",
          automatic_refresh_supported: false,
          automatic_refresh_seconds: null,
        }), { status: 200 });
      }
      return new Response(JSON.stringify({
        status: "ok",
        portfolio: {
          valuation_snapshot_id: "value-1",
          holding_snapshot_id: "holding-1",
          created_at: "2026-09-09T12:00:00Z",
          imported_at: "2026-09-09T11:00:00Z",
          source_as_of: "2026-09-08",
          total_cad: "100",
          priced_positions: 1,
          total_positions: 1,
          position_coverage_pct: "1",
          warnings: [],
          fx: null,
          holdings: [{
            instrument_id: "instrument-1",
            position_id: "position-1",
            canonical_symbol: "ACME.TO",
            security_name: "Acme Inc.",
            asset_type: "STOCK",
            exchange: "TSX",
            trading_currency: "CAD",
            account_alias: "TFSA-01",
            account_type: "TFSA",
            quantity: "2",
            average_cost: "40",
            price: "50",
            price_currency: "CAD",
            market_value_trading: "100",
            market_value_cad: "100",
            unrealized_gain_loss_trading: "20",
            unrealized_gain_loss_cad: "20",
            portfolio_weight: "1",
            price_timestamp: "2026-09-08T20:00:00Z",
            price_fetched_at: "2026-09-09T12:00:00Z",
            price_source: "Synthetic",
            price_source_url: null,
            quote_status: "end_of_day",
            delay_minutes: null,
            price_stale: 0,
            data_status: "end_of_day",
            manual_sector: null,
            sector_source: null,
            sector_source_url: null,
            sector_as_of: null,
          }],
        },
      }), { status: 200 });
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);
    expect(await screen.findByText("SECTOR ALLOCATION")).toBeInTheDocument();
    expect(screen.getByText("CONNECTED · READ ONLY")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Portfolio sector allocation pie chart" })).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "Sector for ACME.TO" })).toBeInTheDocument();
    expect(screen.queryByRole("columnheader", { name: "Account" })).not.toBeInTheDocument();
    expect(screen.queryByRole("columnheader", { name: "Currency" })).not.toBeInTheDocument();
    expect(screen.getByText(/Includes sectors inside ETFs/)).toBeInTheDocument();
    expect(screen.getByText(/STALE = refresh did not return a newer quote/)).toBeInTheDocument();

    fireEvent.click(screen.getByText("COLUMNS 13/16"));
    fireEvent.click(screen.getByRole("checkbox", { name: "Account" }));

    expect(screen.getByRole("columnheader", { name: "Account" })).toBeInTheDocument();
    await waitFor(() => {
      expect(window.localStorage.getItem("portfolio-manager.visible-columns.v1")).toContain("account");
    });

    const deleteButton = screen.getByRole("button", { name: "DELETE ROW" });
    expect(deleteButton).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Select row 1: ACME.TO" }));
    expect(deleteButton).toBeEnabled();
    expect(screen.getByText(/1 row selected/)).toBeInTheDocument();

    fireEvent.keyDown(window, { key: "Delete" });
    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/portfolio/positions/position-1",
        expect.objectContaining({ method: "DELETE" }),
      );
    });
    expect(await screen.findByText(/ACME.TO was removed from the current portfolio snapshot/)).toBeInTheDocument();
  });

  it("automatically prepares but never applies a SnapTrade sync without confirmation", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.includes("/api/snaptrade/sync/pending")) {
        return new Response(JSON.stringify({ preview: null }), { status: 200 });
      }
      if (url.includes("/api/snaptrade/sync/preview")) {
        return new Response(JSON.stringify({
          preview_id: "preview-1",
          created_at: "2026-09-10T15:00:00Z",
          expires_at: "2026-09-10T15:30:00Z",
          holdings_as_of: "2026-09-10T14:30:00Z",
          last_successful_sync_at: "2026-09-10T14:30:00Z",
          positions: [{
            row_number: 1,
            canonical_symbol: "XIC.TO",
            security_name: "Synthetic Canadian ETF",
            asset_type: "ETF",
            exchange: "TSX",
            trading_currency: "CAD",
            quantity: "10",
            average_cost: "31",
            account_alias: "TFSA-TEST",
            account_type: "TFSA",
          }],
          changes: {
            additions: [{ symbol: "XIC.TO", account_type: "TFSA", before: null, after: "10" }],
            removals: [],
            quantity_changes: [],
            cost_basis_changes: [],
            cash_changes: [],
          },
          issues: [],
          error_count: 0,
          warning_count: 0,
          can_apply: true,
        }), { status: 200 });
      }
      if (url.includes("/api/snaptrade/sync/preview-1/apply")) {
        return new Response(JSON.stringify({ status: "ok" }), { status: 200 });
      }
      if (url.includes("/api/snaptrade/status")) {
        return new Response(JSON.stringify({
          adapter_enabled: true,
          connection_status: "connected_read_only",
          connection_permission: "read",
          brokerage_name: "Wealthsimple",
          last_checked_at: "2026-09-10T15:00:00Z",
          last_attempted_sync_at: null,
          last_successful_sync_at: "2026-09-10T14:30:00Z",
          holdings_as_of: "2026-09-10T14:30:00Z",
          next_sync_allowed_at: null,
          sync_allowed: true,
          stale: false,
          warnings: [],
        }), { status: 200 });
      }
      if (url.includes("/api/prices/capabilities")) {
        return new Response(JSON.stringify({ provider: "Synthetic", automatic_refresh_supported: false, automatic_refresh_seconds: null }), { status: 200 });
      }
      if (url.includes("/api/portfolio/history")) return new Response(JSON.stringify({ history: [] }), { status: 200 });
      if (url.includes("/api/portfolio/sectors")) return new Response(JSON.stringify({ analysis: null }), { status: 200 });
      if (url.includes("/api/portfolio")) return new Response(JSON.stringify({ portfolio: null }), { status: 200 });
      throw new Error(`Unexpected request: ${url} ${init?.method ?? "GET"}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);
    expect(await screen.findByText(/SYNC PREVIEW/)).toBeInTheDocument();
    expect(screen.getAllByText("XIC.TO")).toHaveLength(2);
    const applyButton = screen.getByRole("button", { name: "APPLY SNAPSHOT" });
    expect(applyButton).toBeEnabled();
    expect(fetchMock).not.toHaveBeenCalledWith(
      "/api/snaptrade/sync/preview-1/apply",
      expect.anything(),
    );

    fireEvent.click(applyButton);
    expect(await screen.findByText(/Select the required review-confirmation checkbox/)).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalledWith(
      "/api/snaptrade/sync/preview-1/apply",
      expect.anything(),
    );

    fireEvent.click(screen.getByRole("checkbox", { name: /I reviewed every addition/ }));
    expect(applyButton).toBeEnabled();
    fireEvent.click(applyButton);
    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/snaptrade/sync/preview-1/apply",
        expect.objectContaining({ method: "POST" }),
      );
    });
  });
});
