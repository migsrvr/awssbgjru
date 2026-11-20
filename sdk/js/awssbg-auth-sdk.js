/**
 * AWS SBG JRU — Centralized Member Validation SDK (JavaScript / TypeScript ESM)
 * Zero-dependency plug-and-play client for Node.js 18+, Next.js, Express, Bun, and Deno.
 *
 * SECURITY NOTE: Always call this SDK from your backend/server environment where
 * `AWSSBG_API_KEY` is stored in server environment variables (never expose your API key in browser code).
 */

export class AwsSbgAuthError extends Error {
  constructor(message, statusCode = 0, payload = null) {
    super(message);
    this.name = "AwsSbgAuthError";
    this.statusCode = statusCode;
    this.payload = payload;
  }
}

export class AwsSbgAuthClient {
  /**
   * @param {Object} config
   * @param {string} [config.baseUrl="https://awssbgjru.me"] - Base URL of the AWS SBG JRU Portal API
   * @param {string} config.apiKey - Executive-issued API key (`sbg_live_...`)
   * @param {number} [config.timeoutMs=10000] - Request timeout in milliseconds
   * @param {typeof fetch} [config.fetchImpl] - Optional custom fetch implementation for testing
   */
  constructor({ baseUrl = "https://awssbgjru.me", apiKey, timeoutMs = 10000, fetchImpl } = {}) {
    if (!apiKey || typeof apiKey !== "string" || !apiKey.trim()) {
      throw new AwsSbgAuthError("AwsSbgAuthClient requires a non-empty `apiKey` (e.g. process.env.AWSSBG_API_KEY).");
    }
    this.baseUrl = String(baseUrl || "https://awssbgjru.me").replace(/\/+$/, "");
    this.apiKey = apiKey.trim();
    this.timeoutMs = timeoutMs;
    this.fetchImpl = fetchImpl || globalThis.fetch;
  }

  /**
   * Validates an AWS SBG JRU member's Org ID, Username, and Password (strictly read-only).
   *
   * @param {Object} credentials
   * @param {string} credentials.orgId - Unique Org ID (e.g. "AWSSBG-1120-001")
   * @param {string} credentials.username - Member username (e.g. "j.delacruz482")
   * @param {string} credentials.password - Member password
   * @returns {Promise<{valid: boolean, reason: string|null, member: Object|null}>}
   */
  async validateMember({ orgId, username, password } = {}) {
    if (!orgId || !username || !password) {
      throw new AwsSbgAuthError("orgId, username, and password are all required.");
    }

    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), this.timeoutMs);

    try {
      const res = await this.fetchImpl(`${this.baseUrl}/api/v1/external/validate`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Accept": "application/json",
          "X-API-Key": this.apiKey,
        },
        body: JSON.stringify({
          org_id: String(orgId).trim(),
          username: String(username).trim(),
          password: String(password),
        }),
        signal: controller.signal,
      });

      let data = null;
      try {
        data = await res.json();
      } catch (_) {
        data = null;
      }

      if (!res.ok) {
        const detail = (data && (data.detail || data.error)) || `HTTP ${res.status}`;
        throw new AwsSbgAuthError(`AWS SBG validation API error: ${detail}`, res.status, data);
      }

      return {
        valid: Boolean(data && data.valid),
        reason: (data && data.reason) || null,
        member: (data && data.member) || null,
      };
    } finally {
      clearTimeout(timer);
    }
  }

  /**
   * Checks external validation API health.
   * @returns {Promise<{status: string, service: string, version: string}>}
   */
  async checkHealth() {
    const res = await this.fetchImpl(`${this.baseUrl}/api/v1/external/health`, {
      method: "GET",
      headers: { "Accept": "application/json" },
    });
    if (!res.ok) {
      throw new AwsSbgAuthError(`Health check failed with HTTP ${res.status}`, res.status);
    }
    return res.json();
  }
}

export default AwsSbgAuthClient;
