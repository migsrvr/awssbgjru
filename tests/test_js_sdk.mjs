import test from "node:test";
import assert from "node:assert/strict";
import { AwsSbgAuthClient, AwsSbgAuthError } from "../sdk/js/awssbg-auth-sdk.js";

test("AwsSbgAuthClient requires apiKey", () => {
  assert.throws(() => new AwsSbgAuthClient({}), AwsSbgAuthError);
});

test("AwsSbgAuthClient sends X-API-Key header and JSON body to /api/v1/external/validate", async () => {
  let capturedUrl = "";
  let capturedInit = null;

  const mockFetch = async (url, init) => {
    capturedUrl = url;
    capturedInit = init;
    return {
      ok: true,
      status: 200,
      json: async () => ({
        valid: true,
        reason: null,
        member: {
          org_id: "AWSSBG-1120-001",
          username: "j.delacruz482",
          full_name: "Juan Dela Cruz",
          division_name: "Cloud Computing",
          status: "active",
        },
      }),
    };
  };

  const client = new AwsSbgAuthClient({
    baseUrl: "https://awssbgjru.me/",
    apiKey: "sbg_live_testkey123456",
    fetchImpl: mockFetch,
  });

  const res = await client.validateMember({
    orgId: "AWSSBG-1120-001",
    username: "j.delacruz482",
    password: "SecretPw!23",
  });

  assert.equal(capturedUrl, "https://awssbgjru.me/api/v1/external/validate");
  assert.equal(capturedInit.method, "POST");
  assert.equal(capturedInit.headers["X-API-Key"], "sbg_live_testkey123456");
  assert.deepEqual(JSON.parse(capturedInit.body), {
    org_id: "AWSSBG-1120-001",
    username: "j.delacruz482",
    password: "SecretPw!23",
  });
  assert.equal(res.valid, true);
  assert.equal(res.member.full_name, "Juan Dela Cruz");
});

test("AwsSbgAuthClient throws AwsSbgAuthError on 401 unauthorized key", async () => {
  const mockFetch = async () => ({
    ok: false,
    status: 401,
    json: async () => ({ detail: "This API key has been revoked." }),
  });

  const client = new AwsSbgAuthClient({
    apiKey: "sbg_live_revoked",
    fetchImpl: mockFetch,
  });

  await assert.rejects(
    () =>
      client.validateMember({
        orgId: "AWSSBG-1120-001",
        username: "j.delacruz482",
        password: "pw",
      }),
    (err) => err instanceof AwsSbgAuthError && err.statusCode === 401
  );
});
