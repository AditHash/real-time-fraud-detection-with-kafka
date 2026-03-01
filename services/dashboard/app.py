from __future__ import annotations

import os
from collections.abc import AsyncIterator

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse, StreamingResponse


def _alert_service_url() -> str:
    return os.getenv("ALERT_SERVICE_URL", "http://alert-service:8001").rstrip("/")


INDEX_HTML = """<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Fraud Dashboard</title>
    <style>
      :root { color-scheme: dark; }
      body { font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Arial; margin: 0; background: #0b0f14; color: #e6edf3; }
      header { display: flex; gap: 16px; align-items: baseline; padding: 16px 20px; border-bottom: 1px solid #1f2a37; }
      h1 { font-size: 18px; margin: 0; }
      .pill { font-size: 12px; padding: 3px 10px; border-radius: 999px; border: 1px solid #2b3645; color: #9fb0c3; }
      .pill.ok { color: #7ee787; border-color: rgba(126,231,135,.35); }
      .pill.bad { color: #ffa657; border-color: rgba(255,166,87,.35); }
      main { display: grid; grid-template-columns: 380px 1fr; gap: 16px; padding: 16px 20px; }
      .card { border: 1px solid #1f2a37; background: #0f1620; border-radius: 10px; overflow: hidden; }
      .card h2 { font-size: 13px; margin: 0; padding: 12px 14px; border-bottom: 1px solid #1f2a37; color: #9fb0c3; }
      .card .body { padding: 12px 14px; }
      .k { color: #9fb0c3; font-size: 12px; }
      .v { font-size: 14px; }
      .row { display: flex; justify-content: space-between; padding: 6px 0; border-bottom: 1px dashed rgba(31,42,55,.7); }
      .row:last-child { border-bottom: 0; }
      table { width: 100%; border-collapse: collapse; }
      th, td { font-size: 12px; text-align: left; padding: 10px 10px; border-bottom: 1px solid #1f2a37; vertical-align: top; }
      th { color: #9fb0c3; font-weight: 600; }
      code { font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace; font-size: 11px; color: #c9d1d9; }
      .src { text-transform: uppercase; font-size: 11px; letter-spacing: .08em; color: #9fb0c3; }
      .score { font-variant-numeric: tabular-nums; }
      .muted { color: #9fb0c3; font-size: 12px; }
    </style>
  </head>
  <body>
    <header>
      <h1>Fraud Alerts Dashboard</h1>
      <span id="conn" class="pill bad">disconnected</span>
      <span class="pill">SSE + fallback polling</span>
      <span class="muted">Alert source: rule_engine / ml_engine</span>
    </header>
    <main>
      <section class="card">
        <h2>Stats</h2>
        <div class="body">
          <div class="row"><div class="k">Total shown</div><div id="total" class="v">0</div></div>
          <div class="row"><div class="k">Rule alerts</div><div id="rule" class="v">0</div></div>
          <div class="row"><div class="k">ML alerts</div><div id="ml" class="v">0</div></div>
          <div class="row"><div class="k">Last update</div><div id="last" class="v">-</div></div>
        </div>
      </section>
      <section class="card">
        <h2>Latest alerts</h2>
        <div class="body" style="padding:0">
          <table>
            <thead>
              <tr>
                <th>Detected</th>
                <th>Tx</th>
                <th>Source</th>
                <th>Score</th>
                <th>Reason / Model</th>
              </tr>
            </thead>
            <tbody id="rows"></tbody>
          </table>
        </div>
      </section>
    </main>
    <script>
      const rowsEl = document.getElementById('rows');
      const connEl = document.getElementById('conn');
      const totalEl = document.getElementById('total');
      const ruleEl = document.getElementById('rule');
      const mlEl = document.getElementById('ml');
      const lastEl = document.getElementById('last');

      const state = { total: 0, rule: 0, ml: 0, ids: new Set() };

      function setConn(ok) {
        connEl.textContent = ok ? 'connected' : 'disconnected';
        connEl.classList.toggle('ok', ok);
        connEl.classList.toggle('bad', !ok);
      }

      function fmtScore(a) {
        if (a.score === undefined || a.score === null) return '';
        try { return Number(a.score).toFixed(3); } catch { return String(a.score); }
      }

      function addAlert(a) {
        if (!a || !a.alert_id) return;
        if (state.ids.has(a.alert_id)) return;
        state.ids.add(a.alert_id);

        state.total += 1;
        if (a.source === 'rule_engine') state.rule += 1;
        if (a.source === 'ml_engine') state.ml += 1;

        totalEl.textContent = state.total;
        ruleEl.textContent = state.rule;
        mlEl.textContent = state.ml;
        lastEl.textContent = new Date().toLocaleTimeString();

        const tr = document.createElement('tr');
        tr.innerHTML = `
          <td><code>${a.detected_time || ''}</code></td>
          <td><code>${a.transaction_id || ''}</code></td>
          <td class="src">${a.source || ''}</td>
          <td class="score"><code>${fmtScore(a)}</code></td>
          <td><code>${(a.reasons && a.reasons.join(',')) || a.model || ''}</code></td>
        `;
        rowsEl.prepend(tr);

        // keep table small
        while (rowsEl.children.length > 200) rowsEl.removeChild(rowsEl.lastChild);
      }

      async function pollOnce() {
        const res = await fetch('/api/alerts?limit=50&offset=0');
        if (!res.ok) throw new Error('poll failed');
        const data = await res.json();
        for (const item of (data.items || [])) {
          try { addAlert(JSON.parse(item.payload)); } catch {}
        }
      }

      function startSSE() {
        setConn(false);
        const es = new EventSource('/api/stream');
        es.addEventListener('ready', () => setConn(true));
        es.onmessage = (ev) => {
          try { addAlert(JSON.parse(ev.data)); } catch {}
        };
        es.onerror = async () => {
          setConn(false);
          es.close();
          // fallback polling for 30s, then retry SSE
          const until = Date.now() + 30000;
          while (Date.now() < until) {
            try { await pollOnce(); } catch {}
            await new Promise(r => setTimeout(r, 3000));
          }
          startSSE();
        };
      }

      // initial load
      pollOnce().finally(startSSE);
    </script>
  </body>
</html>"""


def create_app() -> FastAPI:
    app = FastAPI(title="Dashboard", version="0.1.0")

    @app.get("/", response_class=HTMLResponse)
    async def index() -> str:
        return INDEX_HTML

    @app.get("/api/alerts")
    async def proxy_alerts(
        limit: int = Query(default=100, ge=1, le=1000),
        offset: int = Query(default=0, ge=0),
    ) -> dict:
        url = f"{_alert_service_url()}/alerts"
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(url, params={"limit": limit, "offset": offset})
        if r.status_code != 200:
            raise HTTPException(status_code=502, detail="alert-service unavailable")
        return r.json()

    @app.get("/api/stream")
    async def proxy_stream() -> StreamingResponse:
        url = f"{_alert_service_url()}/alerts/stream"

        async def gen() -> AsyncIterator[bytes]:
            async with httpx.AsyncClient(timeout=None) as client:
                async with client.stream("GET", url) as r:
                    if r.status_code != 200:
                        raise HTTPException(status_code=502, detail="alert-service unavailable")
                    async for chunk in r.aiter_bytes():
                        yield chunk

        return StreamingResponse(gen(), media_type="text/event-stream")

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8002"))
    uvicorn.run("services.dashboard.app:app", host=host, port=port, log_level="info")

