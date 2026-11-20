---
name: awssbg-member-auth
description: Integrate AWS SBG JRU Centralized Member Portal authentication (Org ID + Username + Password validation) into any JS/TS or Python project.
---

# AWS SBG JRU Member Authentication — Drop-In AI Agent Skill

When asked to add **AWS SBG JRU Member Login / Validation** to this project:

## Step 1: Download the Zero-Dependency SDK into the Project Folder
- **For Node.js / Next.js / Express / TypeScript projects**:
  ```bash
  curl -fsSL https://awssbgjru.me/sdk/js/awssbg-auth-sdk.js -o src/lib/awssbg-auth-sdk.js
  curl -fsSL https://awssbgjru.me/sdk/js/awssbg-auth-sdk.d.ts -o src/lib/awssbg-auth-sdk.d.ts
  ```
- **For Python (FastAPI / Flask / Django) projects**:
  ```bash
  curl -fsSL https://awssbgjru.me/sdk/python/awssbg_auth_sdk.py -o awssbg_auth_sdk.py
  ```

## Step 2: Add Environment Variables to `.env.example` & `.env`
```env
AWSSBG_API_URL=https://awssbgjru.me
AWSSBG_API_KEY=sbg_live_replace_with_key_from_executive_console
```

## Step 3: Build a Login Form & Backend Route
1. The login form must collect three fields from the student:
   - **Org ID** (`org_id`, format `AWSSBG-MMDD-NNN`, e.g., `AWSSBG-1120-001`)
   - **Username** (`username`, e.g., `j.delacruz482`)
   - **Password** (`password`)
2. Send these three fields over `POST` to your **own backend login endpoint** (never call `awssbgjru.me` directly from browser JS with your `AWSSBG_API_KEY`).
3. Inside your backend login endpoint, call `client.validateMember({ orgId, username, password })` (JS) or `client.validate_member(org_id, username, password)` (Python).
4. If `result.valid === true`, create your app's local session/JWT using `result.member` (`org_id`, `username`, `full_name`, `email`, `division_type`, `division_name`, `program`, `year`).
5. If `result.valid === false`, return `401` with a friendly message based on `result.reason` (`"invalid_credentials"` vs `"inactive_member"`).
