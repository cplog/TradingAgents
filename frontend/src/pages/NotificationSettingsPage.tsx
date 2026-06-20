import { useEffect, useState } from "react";
import { v4 as uuidv4 } from "uuid";
import {
  fetchNotificationConfig,
  putNotificationConfig,
  testNotificationChannel,
  type NotificationChannel,
  type NotificationChannelType,
  type NotificationConfig,
} from "../api";
import { PageFrame, PageHeader } from "../components/PageFrame";
import { AppBreadcrumbs } from "../components/navigation/AppBreadcrumbs";
import { useDocumentTitle } from "../hooks/useDocumentTitle";

const CHANNEL_TYPE_LABELS: Record<NotificationChannelType, string> = {
  webhook: "Webhook",
  telegram: "Telegram",
  slack: "Slack",
  email: "Email (SMTP)",
  discord: "Discord",
};

const DEFAULT_CONFIG: NotificationConfig = {
  enabled: false,
  quiet_hours_start: null,
  quiet_hours_end: null,
  channels: [],
  dedupe_minutes: 15,
};

export function NotificationSettingsPage() {
  useDocumentTitle("Notifications");
  const [config, setConfig] = useState<NotificationConfig | null>(null);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    void fetchNotificationConfig()
      .then(setConfig)
      .catch(() => setConfig(DEFAULT_CONFIG));
  }, []);

  const update = (patch: Partial<NotificationConfig>) => {
    setConfig((prev) => (prev ? { ...prev, ...patch } : { ...DEFAULT_CONFIG, ...patch }));
  };

  const handleSave = async () => {
    if (!config) return;
    setSaving(true);
    setMessage(null);
    try {
      const saved = await putNotificationConfig(config);
      setConfig(saved);
      setMessage("Saved.");
    } catch (e) {
      setMessage("Failed to save.");
    } finally {
      setSaving(false);
    }
  };

  const addChannel = (type: NotificationChannelType) => {
    const channel: NotificationChannel = {
      id: uuidv4(),
      type,
      name: `${CHANNEL_TYPE_LABELS[type]} alerts`,
      enabled: true,
      config: {},
    };
    update({ channels: [...(config?.channels ?? []), channel] });
  };

  const updateChannel = (id: string, patch: Partial<NotificationChannel>) => {
    update({
      channels: (config?.channels ?? []).map((c) => (c.id === id ? { ...c, ...patch } : c)),
    });
  };

  const removeChannel = (id: string) => {
    update({ channels: (config?.channels ?? []).filter((c) => c.id !== id) });
  };

  if (!config) {
    return (
      <PageFrame className="content-entrance">
        <PageHeader title="Notifications" description="Loading..." />
      </PageFrame>
    );
  }

  return (
    <PageFrame className="content-entrance">
      <PageHeader
        title="Notifications"
        description="Configure channels for monitor and topics alerts."
        meta={<AppBreadcrumbs items={[{ label: "System" }, { label: "Notifications" }]} />}
      />

      {message && (
        <div className="page-section section-gap" style={{ marginBottom: 20 }}>
          {message}
        </div>
      )}

      <section className="page-section section-gap">
        <h2 style={{ marginTop: 0 }}>Global settings</h2>
        <label className="ui-field">
          <span className="ui-field__label">Enable notifications</span>
          <select
            className="ui-input"
            value={config.enabled ? "true" : "false"}
            onChange={(e) => update({ enabled: e.target.value === "true" })}
          >
            <option value="false">Disabled</option>
            <option value="true">Enabled</option>
          </select>
        </label>
        <div style={{ display: "flex", gap: "1rem" }}>
          <label className="ui-field" style={{ flex: 1 }}>
            <span className="ui-field__label">Quiet hours start (HH:MM)</span>
            <input
              className="ui-input"
              placeholder="22:00"
              value={config.quiet_hours_start ?? ""}
              onChange={(e) => update({ quiet_hours_start: e.target.value || null })}
            />
          </label>
          <label className="ui-field" style={{ flex: 1 }}>
            <span className="ui-field__label">Quiet hours end (HH:MM)</span>
            <input
              className="ui-input"
              placeholder="08:00"
              value={config.quiet_hours_end ?? ""}
              onChange={(e) => update({ quiet_hours_end: e.target.value || null })}
            />
          </label>
        </div>
        <label className="ui-field">
          <span className="ui-field__label">Dedupe window (minutes)</span>
          <input
            className="ui-input"
            type="number"
            min={0}
            max={1440}
            value={config.dedupe_minutes}
            onChange={(e) => update({ dedupe_minutes: Number(e.target.value) })}
          />
        </label>
      </section>

      <section className="page-section section-gap">
        <h2 style={{ marginTop: 0 }}>Channels</h2>
        {(config.channels ?? []).map((channel) => (
          <ChannelEditor
            key={channel.id}
            channel={channel}
            onChange={(patch) => updateChannel(channel.id, patch)}
            onRemove={() => removeChannel(channel.id)}
          />
        ))}
        <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", marginTop: 12 }}>
          {Object.entries(CHANNEL_TYPE_LABELS).map(([type, label]) => (
            <button
              key={type}
              className="ui-btn-secondary"
              onClick={() => addChannel(type as NotificationChannelType)}
            >
              + {label}
            </button>
          ))}
        </div>
      </section>

      <section className="page-section section-gap">
        <button className="ui-btn-primary" disabled={saving} onClick={handleSave}>
          {saving ? "Saving..." : "Save notification settings"}
        </button>
      </section>
    </PageFrame>
  );
}

function ChannelEditor({
  channel,
  onChange,
  onRemove,
}: {
  channel: NotificationChannel;
  onChange: (patch: Partial<NotificationChannel>) => void;
  onRemove: () => void;
}) {
  const [testMsg, setTestMsg] = useState("Test notification from TradingAgents");
  const [testResult, setTestResult] = useState<string | null>(null);

  const handleTest = async () => {
    setTestResult("Sending...");
    try {
      const res = await testNotificationChannel(channel.id, testMsg);
      setTestResult(res.ok ? "Sent successfully." : `Failed: ${res.error ?? "unknown"}`);
    } catch (e) {
      setTestResult("Failed to send test.");
    }
  };

  return (
    <div style={{ borderBottom: "1px solid var(--color-canvas-fog)", padding: "12px 0" }}>
      <div style={{ display: "flex", gap: "1rem", alignItems: "center" }}>
        <label className="ui-field" style={{ flex: 1 }}>
          <span className="ui-field__label">Name</span>
          <input
            className="ui-input"
            value={channel.name}
            onChange={(e) => onChange({ name: e.target.value })}
          />
        </label>
        <label className="ui-field">
          <span className="ui-field__label">Enabled</span>
          <select
            className="ui-input"
            value={channel.enabled ? "true" : "false"}
            onChange={(e) => onChange({ enabled: e.target.value === "true" })}
          >
            <option value="true">Yes</option>
            <option value="false">No</option>
          </select>
        </label>
        <button className="ui-btn-danger" onClick={onRemove}>Remove</button>
      </div>
      <ChannelFields channel={channel} onChange={onChange} />
      <div style={{ display: "flex", gap: "0.5rem", marginTop: 8 }}>
        <input
          className="ui-input"
          style={{ flex: 1 }}
          value={testMsg}
          onChange={(e) => setTestMsg(e.target.value)}
        />
        <button className="ui-btn-secondary" onClick={handleTest}>Test</button>
      </div>
      {testResult && <div style={{ fontSize: 14, marginTop: 4 }}>{testResult}</div>}
    </div>
  );
}

function ChannelFields({
  channel,
  onChange,
}: {
  channel: NotificationChannel;
  onChange: (patch: Partial<NotificationChannel>) => void;
}) {
  const setConfig = (patch: Record<string, unknown>) =>
    onChange({ config: { ...channel.config, ...patch } });

  switch (channel.type) {
    case "webhook":
      return (
        <>
          <Field label="URL" value={String(channel.config.url ?? "")} onChange={(v) => setConfig({ url: v })} />
          <Field label="Method" value={String(channel.config.method ?? "POST")} onChange={(v) => setConfig({ method: v })} />
        </>
      );
    case "telegram":
      return (
        <>
          <Field label="Bot token" value={String(channel.config.bot_token ?? "")} onChange={(v) => setConfig({ bot_token: v })} />
          <Field label="Chat ID" value={String(channel.config.chat_id ?? "")} onChange={(v) => setConfig({ chat_id: v })} />
        </>
      );
    case "slack":
      return (
        <>
          <Field label="Webhook URL" value={String(channel.config.webhook_url ?? "")} onChange={(v) => setConfig({ webhook_url: v })} />
          <Field label="Token (optional)" value={String(channel.config.token ?? "")} onChange={(v) => setConfig({ token: v })} />
          <Field label="Channel ID (optional)" value={String(channel.config.channel_id ?? "")} onChange={(v) => setConfig({ channel_id: v })} />
        </>
      );
    case "email":
      return (
        <>
          <Field label="SMTP host" value={String(channel.config.smtp_host ?? "")} onChange={(v) => setConfig({ smtp_host: v })} />
          <Field label="SMTP port" value={String(channel.config.smtp_port ?? "")} onChange={(v) => setConfig({ smtp_port: v })} />
          <Field label="SMTP user" value={String(channel.config.smtp_user ?? "")} onChange={(v) => setConfig({ smtp_user: v })} />
          <Field label="SMTP password" value={String(channel.config.smtp_password ?? "")} onChange={(v) => setConfig({ smtp_password: v })} type="password" />
          <Field label="To" value={String(channel.config.to ?? "")} onChange={(v) => setConfig({ to: v })} />
        </>
      );
    case "discord":
      return (
        <Field label="Webhook URL" value={String(channel.config.webhook_url ?? "")} onChange={(v) => setConfig({ webhook_url: v })} />
      );
    default:
      return null;
  }
}

function Field({
  label,
  value,
  onChange,
  type = "text",
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  type?: string;
}) {
  return (
    <label className="ui-field">
      <span className="ui-field__label">{label}</span>
      <input className="ui-input" type={type} value={value} onChange={(e) => onChange(e.target.value)} />
    </label>
  );
}
