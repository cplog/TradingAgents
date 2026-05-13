export function AdminPage() {
  return (
    <div style={{ maxWidth: "720px" }}>
      <h1 style={{ marginTop: 0 }}>External administration</h1>
      <p style={{ color: "var(--color-ash-gray)" }}>
        This deployment uses optional{" "}
        <strong>Cloudflare KV</strong> for durable API state instead of Redis Commander or MongoDB
        Express. Use the Cloudflare dashboard to inspect namespace keys, or keep the default local
        JSON file at <span className="mono">~/.tradingagents/api_state.json</span>.
      </p>
      <ul>
        <li>
          <a href="https://dash.cloudflare.com/" target="_blank" rel="noreferrer">
            Cloudflare Dashboard
          </a>{" "}
          (Workers → KV)
        </li>
        <li>
          <a href="https://fastapi.tiangolo.com/" target="_blank" rel="noreferrer">
            FastAPI docs
          </a>{" "}
          for this service live at <span className="mono">/docs</span> when the API is running.
        </li>
      </ul>
      <p style={{ fontSize: 14 }}>
        To add Mongo Express or Redis Commander, extend{" "}
        <span className="mono">docker-compose.yml</span> on your fork; they are not bundled here.
      </p>
    </div>
  );
}
