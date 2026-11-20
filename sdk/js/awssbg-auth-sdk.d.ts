export interface AwsSbgMemberProfile {
  org_id: string;
  username: string;
  first_name: string;
  last_name: string;
  full_name: string;
  email: string;
  student_id: string | null;
  year: string | null;
  program: string | null;
  division_type: string | null;
  division_name: string | null;
  status: "active" | "suspended" | "revoked";
  must_change_password: boolean;
}

export interface AwsSbgValidateResult {
  valid: boolean;
  reason: "invalid_credentials" | "inactive_member" | null;
  member: AwsSbgMemberProfile | null;
}

export interface AwsSbgAuthClientConfig {
  baseUrl?: string;
  apiKey: string;
  timeoutMs?: number;
  fetchImpl?: typeof fetch;
}

export class AwsSbgAuthError extends Error {
  statusCode: number;
  payload: unknown;
  constructor(message: string, statusCode?: number, payload?: unknown);
}

export class AwsSbgAuthClient {
  constructor(config: AwsSbgAuthClientConfig);
  validateMember(credentials: {
    orgId: string;
    username: string;
    password: string;
  }): Promise<AwsSbgValidateResult>;
  checkHealth(): Promise<{ status: string; service: string; version: string }>;
}

export default AwsSbgAuthClient;
