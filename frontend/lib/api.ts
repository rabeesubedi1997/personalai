const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(
  path: string,
  options: { method?: string; token?: string | null; body?: unknown; params?: Record<string, string | boolean | undefined> } = {}
): Promise<T> {
  const url = new URL(`${API_BASE_URL}${path}`);
  if (options.params) {
    for (const [key, value] of Object.entries(options.params)) {
      if (value !== undefined) url.searchParams.set(key, String(value));
    }
  }
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (options.token) headers["Authorization"] = `Bearer ${options.token}`;

  const res = await fetch(url.toString(), {
    method: options.method ?? "GET",
    headers,
    body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
    cache: "no-store",
  });

  if (!res.ok) {
    let detail = `Request failed: ${res.status}`;
    try {
      const body = await res.json();
      if (body.detail) detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      // ignore — use default detail
    }
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

// --- Types ---

export type HealthStatus = { status: string; database: string; redis: string; ai_provider: string };

export type User = {
  id: string;
  tenant_id: string;
  email: string;
  full_name: string;
  role: string;
  is_active: boolean;
};

export type AgentInfo = { name: string; description: string; allowed_tools: string[] };

export type ToolTraceEntry = { tool: string; arguments: Record<string, unknown>; result: string; is_error: boolean };

export type AgentRunResponse = {
  run_id: string;
  agent: string;
  status: string;
  final_response: string;
  iterations: number;
  tool_trace: ToolTraceEntry[];
  model: string;
  error: string | null;
  approval_id: string | null;
  conversation_id: string | null;
};

export type MarketplaceAgent = {
  slug: string;
  name: string;
  description: string;
  category: string;
  version: string;
  installed: boolean;
};

export type Approval = {
  id: string;
  tenant_id: string;
  agent_run_id: string | null;
  agent_name: string;
  tool_name: string;
  arguments: Record<string, unknown>;
  status: "pending" | "rejected" | "executed" | "failed";
  decided_by_user_id: string | null;
  decision_note: string | null;
  result: { content: string; data: Record<string, unknown> } | null;
  error: string | null;
  created_at: string;
  updated_at: string;
};

export type Plan = {
  id: string;
  slug: string;
  name: string;
  price_usd_per_month: number;
  max_agent_runs_per_month: number;
  max_tool_calls_per_month: number;
  max_users: number;
};

export type Subscription = {
  tenant_id: string;
  plan: Plan;
  status: string;
  current_period_agent_runs: number;
};

export type Notification = {
  id: string;
  tenant_id: string;
  user_id: string;
  channel: string;
  subject: string;
  message: string;
  status: string;
  is_read: boolean;
  metadata: Record<string, unknown>;
  error: string | null;
  created_at: string;
};

export type ApiKey = {
  id: string;
  agent_slug: string;
  label: string;
  key_prefix: string;
  is_active: boolean;
  last_used_at: string | null;
  created_at: string;
};

export type BusinessConnector = {
  id: string;
  business_slug: string;
  base_url: string;
  is_enabled: boolean;
  extra_config: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
};

export type AvailableBusiness = {
  business_slug: string;
  name: string;
  description: string;
  connector: BusinessConnector | null;
};

export type ApiKeyCreated = ApiKey & { api_key: string };

export type TenantSummary = {
  id: string;
  name: string;
  slug: string;
  is_active: boolean;
  user_count: number;
  plan_slug: string | null;
  current_period_agent_runs: number;
  created_at: string;
};

// --- Auth ---

export const fetchHealth = () => request<HealthStatus>("/api/v1/health");

export async function login(email: string, password: string): Promise<string> {
  const data = await request<{ access_token: string }>("/api/v1/auth/login", {
    method: "POST",
    body: { email, password },
  });
  return data.access_token;
}

export const bootstrap = (email: string, password: string) =>
  request<User>("/api/v1/auth/bootstrap", { method: "POST", body: { email, password } });

export const fetchMe = (token: string) => request<User>("/api/v1/auth/me", { token });

// --- Agents ---

export const listAgents = (token: string) => request<AgentInfo[]>("/api/v1/agents", { token });

export const runAgent = (token: string, agent: string, message: string, conversation_id?: string | null) =>
  request<AgentRunResponse>("/api/v1/agents/run", {
    method: "POST",
    token,
    body: { agent, message, conversation_id: conversation_id ?? undefined },
  });

// --- Marketplace ---

export const listMarketplace = (token: string) =>
  request<MarketplaceAgent[]>("/api/v1/marketplace/agents", { token });

export const installAgent = (token: string, slug: string) =>
  request(`/api/v1/marketplace/agents/${slug}/install`, { method: "POST", token });

export const uninstallAgent = (token: string, slug: string) =>
  request(`/api/v1/marketplace/agents/${slug}/uninstall`, { method: "POST", token });

// --- Approvals ---

export const listApprovals = (token: string, status?: string) =>
  request<Approval[]>("/api/v1/approvals", { token, params: { status } });

export const approveApproval = (token: string, id: string, note?: string) =>
  request<Approval>(`/api/v1/approvals/${id}/approve`, { method: "POST", token, body: { note } });

export const rejectApproval = (token: string, id: string, note?: string) =>
  request<Approval>(`/api/v1/approvals/${id}/reject`, { method: "POST", token, body: { note } });

// --- Billing ---

export const getSubscription = (token: string) => request<Subscription>("/api/v1/billing/subscription", { token });

export const listPlans = (token: string) => request<Plan[]>("/api/v1/billing/plans", { token });

export const updateSubscription = (token: string, plan_slug: string) =>
  request<Subscription>("/api/v1/billing/subscription", { method: "POST", token, body: { plan_slug } });

// --- Notifications ---

export const listNotifications = (token: string, unread_only?: boolean) =>
  request<Notification[]>("/api/v1/notifications", { token, params: { unread_only } });

export const markNotificationRead = (token: string, id: string) =>
  request<Notification>(`/api/v1/notifications/${id}/read`, { method: "POST", token });

// --- Admin ---

export const listAdminTenants = (token: string) => request<TenantSummary[]>("/api/v1/admin/tenants", { token });

// --- Integrations (agent API keys for embedding a chat widget elsewhere) ---

export const listApiKeys = (token: string) => request<ApiKey[]>("/api/v1/integrations/api-keys", { token });

export const createApiKey = (token: string, agent_slug: string, label: string) =>
  request<ApiKeyCreated>("/api/v1/integrations/api-keys", {
    method: "POST",
    token,
    body: { agent_slug, label },
  });

export const revokeApiKey = (token: string, id: string) =>
  request<ApiKey>(`/api/v1/integrations/api-keys/${id}`, { method: "DELETE", token });

// --- Business connectors (point a business module at a real API instead of its mock) ---

export const listBusinessConnectors = (token: string) =>
  request<AvailableBusiness[]>("/api/v1/business-connectors", { token });

export const setBusinessConnector = (
  token: string,
  businessSlug: string,
  base_url: string,
  extra_config?: Record<string, unknown>
) =>
  request<BusinessConnector>(`/api/v1/business-connectors/${businessSlug}`, {
    method: "PUT",
    token,
    body: { base_url, extra_config },
  });

export const deleteBusinessConnector = (token: string, businessSlug: string) =>
  request<void>(`/api/v1/business-connectors/${businessSlug}`, { method: "DELETE", token });
