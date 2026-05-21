import { PageFrame, PageHeader } from "../components/PageFrame";

export function AdminPage() {
  return (
    <PageFrame>
      <PageHeader
        title="External administration"
        description="Optional Cloudflare KV for durable API state, or local JSON at ~/.tradingagents/api_state.json."
      />
      <div className="panel">
        <div className="panel__body">
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
              for this service at <span className="mono">/docs</span> when the API is running.
            </li>
          </ul>
          <p className="notice">
            To add Mongo Express or Redis Commander, extend{" "}
            <span className="mono">docker-compose.yml</span> on your fork; they are not bundled here.
          </p>
        </div>
      </div>
    </PageFrame>
  );
}
