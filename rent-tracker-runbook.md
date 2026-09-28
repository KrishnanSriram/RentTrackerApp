# Rent Tracker: Serverless Backend Runbook

**As of:** 2026-09-28 · **Environment:** KrishRentTracker-Dev · **Region:** us-east-2 (Ohio)

This runbook rebuilds the rent tracker's backend from an empty AWS account, and tears it down again. It follows the order it was built in: account access, DynamoDB, Cognito, IAM, Lambda, API Gateway, then tests. The full Lambda source code is in the appendices, so this one file is all you need.

**Status:** all four services are deployed and pass every test in [Step 7](#step-7-test-everything). The React frontend (Cognito sign-in, new API paths, S3 hosting) is the next piece of work.

---

## Contents

- [Architecture](#architecture)
- [Current values (Dev)](#current-values-dev)
- [Prerequisites](#prerequisites)
- [Step 1: Account, access and CLI](#step-1-account-access-and-cli)
- [Step 2: DynamoDB table](#step-2-dynamodb-table)
- [Step 3: Cognito user pool](#step-3-cognito-user-pool)
- [Step 4: IAM role for Lambda](#step-4-iam-role-for-lambda)
- [Step 5: Lambda functions](#step-5-lambda-functions)
- [Step 6: API Gateway](#step-6-api-gateway)
- [Step 7: Test everything](#step-7-test-everything)
- [Troubleshooting](#troubleshooting)
- [Teardown](#teardown)
- [What's next](#whats-next)
- [Appendix A: API reference](#appendix-a-api-reference)
- [Appendix B–E: Lambda source code](#appendix-b-rent-properties)

---

## Architecture

```
                      sign in
   ┌───────────┐ ─────────────────► ┌──────────────────────┐
   │ React app │                    │ Amazon Cognito       │
   │ (browser) │ ◄───── token ───── │ user pool + client   │
   └─────┬─────┘                    └──────────┬───────────┘
         │ Authorization: Bearer <token>       │ trusts issuer
         ▼                                     ▼
   ┌─────────────────────────────────────────────────────┐
   │ API Gateway (HTTP API)                              │
   │ JWT authorizer · CORS · 17 routes · $default stage  │
   └───┬──────────────┬──────────────┬──────────────┬────┘
       ▼              ▼              ▼              ▼
 rent-properties  rent-renters  rent-payments  rent-dashboard   (Lambda, Python 3.13, arm64)
       └──────────────┴──────┬───────┴──────────────┘
                             ▼
                 DynamoDB table: RentTracker (on-demand)
```

| Before (Docker) | After (serverless) |
| --- | --- |
| Login service issuing its own JWTs | Cognito user pool |
| nginx gateway routing by path | API Gateway HTTP API with a JWT authorizer |
| Properties, Renters, Payments, Dashboard containers | Four Lambda functions |
| Postgres, one database per service | One DynamoDB table |
| ~$95–110/month on ECS Fargate | Under $1/month at 10–50 calls a day |

---

## Current values (Dev)

These are the IDs of the running Dev environment. **A rebuild creates new ones** for the user pool, app client and API; update this table and your shell variables when that happens.

| Item | Value |
| --- | --- |
| Management account | Krishnan79 (`855575884768`) |
| Organization ID | `o-kt88d1qw6u` |
| OU | KrishRentTracker (`ou-ys4e-e4rv7kki`) |
| Dev account | KrishRentTracker-Dev (`322037002205`) |
| Identity Center portal | `https://d-90667e1f8f.awsapps.com/start` (Identity Center region: **us-east-1**) |
| CLI profile | `krishrent-dev` |
| App region | `us-east-2` |
| DynamoDB table | `RentTracker` |
| Cognito user pool | `rent-tracker-users` · `us-east-2_buHZ4Y9vJ` |
| Cognito app client | `rent-tracker-web` · `4fss6ia5mf1iuj2bj1q0jq0ncs` |
| Cognito issuer | `https://cognito-idp.us-east-2.amazonaws.com/us-east-2_buHZ4Y9vJ` |
| IAM role | `rent-tracker-lambda-role` |
| Lambda functions | `rent-properties`, `rent-renters`, `rent-payments`, `rent-dashboard` |
| HTTP API | `rent-tracker-api` · `xd30d9fz0c` |
| API URL | `https://xd30d9fz0c.execute-api.us-east-2.amazonaws.com` |

Keep this file private: it holds account IDs. For anything public, replace them with placeholders.

---

## Prerequisites

- An AWS Organization with a management account (see Step 1).
- **AWS CLI v2.** Windows: `winget install -e --id Amazon.AWSCLI`. Ubuntu/WSL: see the AWS CLI install guide.
- **bash with `jq`** for the tests (`sudo apt install -y jq` on Ubuntu/WSL). PowerShell equivalents are noted where they differ.
- The Lambda source files from Appendices B–E.

**Shell notes (bash):**

- Capture command output with `$(...)`: `TOKEN=$(aws ...)`, never `TOKEN=aws ...`.
- Put passwords containing `!` in single quotes.
- A variable like `H="Authorization: Bearer $TOKEN"` stores the token's value when set. Re-set `H` after refreshing `TOKEN`.

**PowerShell notes:** continue lines with a backtick (`` ` ``), use `curl.exe` (plain `curl` is a different command), and use `Invoke-RestMethod` for JSON bodies.

---

## Step 1: Account, access and CLI

### 1.1 Organization structure

```
Root
├── Krishnan79 (management account): Organizations, Identity Center, billing. No workloads.
├── OU: KrishRentTracker
│   ├── KrishRentTracker-Dev    ← everything in this runbook
│   ├── KrishRentTracker-IT     (same setup, when needed)
│   └── KrishRentTracker-Prod   (same setup, when needed)
├── OU: EshwarPalmistry
└── OU: SathyaRental
```

The management account stays at Root. Service control policies never apply to it, so moving it into an OU gains nothing. Never close it: that would dissolve the organization.

### 1.2 Create an account (management account, AWS Organizations)

1. **AWS Organizations → AWS accounts → Add an AWS account → Create.**
2. Name `KrishRentTracker-<Env>`; email `krishnan79.sriram+krishrent-<env>@gmail.com` (plus-addressing gives each account a unique email with one inbox).
3. Move it into the `KrishRentTracker` OU.
4. Leave the new account's root user alone. It has no password, and all access goes through Identity Center.

### 1.3 Give yourself access (management account, IAM Identity Center, us-east-1)

1. **Users:** create your user if it doesn't exist; set up MFA.
2. **Permission sets:** create one from the predefined **AdministratorAccess** policy (once). Under **Edit → Session duration**, set **12 hours**.
3. **Multi-account permissions → AWS accounts:** expand the OU with its **▶ arrow**, tick the **account's** checkbox (not the OU's), then **Assign users or groups** → your user → AdministratorAccess.
4. **Settings → Authentication:** lengthen the portal session; leave MFA prompting "only when sign-in context changes".
5. Optional: also assign yourself AdministratorAccess on the management account, so you stop signing in as root day to day. Make sure the root user has MFA.

### 1.4 Sign in to the console

- Portal: `https://d-90667e1f8f.awsapps.com/start` → expand the account → **AdministratorAccess**.
- Direct bookmark for the Dev console:

```
https://d-90667e1f8f.awsapps.com/start/#/console?account_id=322037002205&role_name=AdministratorAccess
```

- In the console, **switch the region to US East (Ohio) us-east-2** before creating anything.
- Optional: account menu → **Turn on multi-session support** to be signed in to several accounts at once.

### 1.5 Connect the CLI

```bash
aws configure sso
#   SSO session name:        krishrent
#   SSO start URL:           https://d-90667e1f8f.awsapps.com/start
#   SSO region:              us-east-1        <- Identity Center's region, NOT the app region
#   SSO registration scopes: (Enter for default)
#   → browser opens: sign in with your Identity Center username (not the root email), Allow
#   Account:                 322037002205
#   Role:                    AdministratorAccess
#   Default client region:   us-east-2        <- the app region
#   Output format:           json
#   Profile name:            krishrent-dev

export AWS_PROFILE=krishrent-dev              # PowerShell: $env:AWS_PROFILE = "krishrent-dev"
                                              # persistent on Windows: setx AWS_PROFILE krishrent-dev
aws sts get-caller-identity                   # "Account" must be 322037002205
```

When the session expires, run `aws sso login`.

### 1.6 Budget alert (management account)

**Billing and Cost Management → Budgets → Create budget:** monthly cost budget, **$5**, filtered to linked account `322037002205`, alerts at **80% actual** and **100% forecasted**.

---

## Step 2: DynamoDB table

### 2.1 Specs

| Setting | Value |
| --- | --- |
| Table name | `RentTracker` |
| Partition key | `PK` (String) |
| Sort key | `SK` (String) |
| Capacity mode | On-demand |
| Table class | DynamoDB Standard |
| Secondary indexes | None |
| Encryption | AWS owned key (default) |
| Deletion protection | On |
| Point-in-time recovery | On |
| Tag | `app = rent-tracker` |

### 2.2 Create it

Console: **DynamoDB → Create table**, enter the values above (choose **Customize settings** to set on-demand and deletion protection), then **Backups → Point-in-time recovery → On**.

Or from the CLI:

```bash
aws dynamodb create-table --table-name RentTracker \
  --attribute-definitions AttributeName=PK,AttributeType=S AttributeName=SK,AttributeType=S \
  --key-schema AttributeName=PK,KeyType=HASH AttributeName=SK,KeyType=RANGE \
  --billing-mode PAY_PER_REQUEST --deletion-protection-enabled \
  --tags Key=app,Value=rent-tracker --region us-east-2

aws dynamodb update-continuous-backups --table-name RentTracker --region us-east-2 \
  --point-in-time-recovery-specification PointInTimeRecoveryEnabled=true

aws dynamodb describe-table --table-name RentTracker --region us-east-2 \
  --query "Table.[TableStatus,KeySchema]"        # expect ACTIVE, PK HASH, SK RANGE
```

### 2.3 Key design (single table)

| Record | PK | SK | Attributes |
| --- | --- | --- | --- |
| Property | `USER#<sub>` | `PROPERTY#<propertyId>` | id, address, monthlyRent?, createdAt, updatedAt |
| Renter | `USER#<sub>#PROPERTY#<propertyId>` | `RENTER#<renterId>` | id, propertyId, name, email, phone, contactType |
| Payment | `USER#<sub>#PROPERTY#<propertyId>` | `PAYMENT#<yyyy-mm>#<paymentId>` | id, propertyId, amount, month, paidOn, method?, renterId?, renterName?, note? |

- `<sub>` is the user's Cognito ID from their token, so every key is scoped to one user.
- A property's renters and payments share one partition: deleting a property is one query plus a batch delete.
- The month in the payment's sort key lets one query fetch a single month.
- No records are created by hand; the Lambda functions write them.

---

## Step 3: Cognito user pool

### 3.1 Create the pool and app client

1. **Cognito → User pools → Create user pool.**
2. Application type: **Single-page application (SPA)**. App name: `rent-tracker-web`.
3. Sign-in identifiers: **Email** only. Required attribute: email.
4. Self-registration: **off** (only users you create can sign in; turn on later if others should sign up).
5. Return URL: `http://localhost:5173`.
6. **Create user directory.**

### 3.2 Adjust settings

| Where | Setting |
| --- | --- |
| User pool → rename | `rent-tracker-users` |
| Settings | Deletion protection **on** |
| App client → Edit → Authentication flows | Add **ALLOW_USER_PASSWORD_AUTH** (CLI testing only; remove once the React app handles sign-in) |
| App client → Login pages → Edit | Allowed callback URL `http://localhost:5173`; **Allowed sign-out URL `http://localhost:5173`** |
| Feature plan | Essentials (free up to 10,000 monthly active users) |

Verify on the app client page:

| Setting | Expected |
| --- | --- |
| Client secret | `-` (none) |
| Authentication flows | Choice-based sign-in, Username and password, SRP, refresh tokens |
| OAuth grant type | Authorization code grant |
| Scopes | openid, email (phone is harmless) |
| Token lifetimes | Access 60 min, ID 60 min, refresh 5 days |

Note the **user pool ID**, **client ID** and **Cognito domain** (Branding → Domain). None is secret; the client ID goes into the React app.

### 3.3 Create a user and get a token

Console: **Users → Create user** → Don't send an invitation → email → **Mark email address as verified** → set a password. The console only sets a temporary password, so make it permanent:

```bash
POOL="us-east-2_buHZ4Y9vJ"
CLIENT="4fss6ia5mf1iuj2bj1q0jq0ncs"
EMAIL="your-email"

aws cognito-idp admin-set-user-password --user-pool-id "$POOL" --username "$EMAIL" \
  --password 'Test-Passw0rd!' --permanent --region us-east-2
```

Or create the user entirely from the CLI:

```bash
aws cognito-idp admin-create-user --user-pool-id "$POOL" --username "$EMAIL" \
  --user-attributes Name=email,Value="$EMAIL" Name=email_verified,Value=true \
  --message-action SUPPRESS --region us-east-2
aws cognito-idp admin-set-user-password --user-pool-id "$POOL" --username "$EMAIL" \
  --password 'Test-Passw0rd!' --permanent --region us-east-2
```

Get an access token:

```bash
TOKEN=$(aws cognito-idp initiate-auth --client-id "$CLIENT" --auth-flow USER_PASSWORD_AUTH \
  --auth-parameters USERNAME="$EMAIL",PASSWORD='Test-Passw0rd!' \
  --query "AuthenticationResult.AccessToken" --output text --region us-east-2)
echo "${TOKEN:0:30}"        # starts with eyJ
```

The token's claims (the middle, base64 part) include `iss` (the pool), `client_id` (the app client), `token_use: access`, and `sub` (the user's ID, e.g. `51ebc570-f041-70cc-5ac0-79f6177137cb` for the current test user). Tokens expire after 60 minutes. Treat them like passwords.

---

## Step 4: IAM role for Lambda

1. **IAM → Roles → Create role** → Trusted entity **AWS service** → Use case **Lambda**.
2. Attach **AWSLambdaBasicExecutionRole** (CloudWatch logs).
3. Role name: `rent-tracker-lambda-role`.
4. **Add permissions → Create inline policy → JSON**, name `rent-tracker-dynamodb`:

```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Action": ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem",
               "dynamodb:DeleteItem", "dynamodb:Query", "dynamodb:BatchWriteItem"],
    "Resource": "arn:aws:dynamodb:us-east-2:322037002205:table/RentTracker"
  }]
}
```

Change the account ID when rebuilding in another account. Payments' DynamoDB transaction (moving a payment to another month) is authorized by PutItem and DeleteItem, so nothing more is needed.

Optional refinement: give `rent-dashboard` its own role with only `GetItem` and `Query`.

---

## Step 5: Lambda functions

### 5.1 Common settings (all four)

| Setting | Value |
| --- | --- |
| Author from scratch | yes |
| Runtime | Python 3.13 (or newest Python offered) |
| Architecture | arm64 |
| Execution role | Use an existing role → `rent-tracker-lambda-role` |
| Handler | `lambda_function.lambda_handler` (default) |
| Environment variable | `TABLE_NAME` = `RentTracker` |
| Memory | **256 MB** (the 128 MB default runs at ~98 MB used) |
| Timeout | **10 seconds** (the 3-second default is tight on cold starts) |

For each function: **Lambda → Create function** with the settings above → replace **all** of `lambda_function.py` with the code from its appendix → **Deploy** → set the environment variable → **Configuration → General configuration → Edit** for memory and timeout.

| Function | Code | Purpose |
| --- | --- | --- |
| `rent-properties` | Appendix B | Properties (address, optional monthly rent); deleting one also deletes its renters and payments |
| `rent-renters` | Appendix C | Renters per property; primary/secondary contact; email and phone validation |
| `rent-payments` | Appendix D | Payments per property; any number per month; moving a payment to another month is atomic |
| `rent-dashboard` | Appendix E | Read-only: monthly status per property and per-property history |

No packaging is needed; `boto3` is built into the Lambda runtime.

### 5.2 Console test events

Each function can be tested before the API exists. Replace the `sub` with your user's, and the IDs with ones from earlier results. A test using your real `sub` creates real data that later shows up through the API.

**rent-properties**: expect `201`:

```json
{
  "routeKey": "POST /api/properties",
  "body": "{\"address\": \"12 Oak St\", \"monthlyRent\": 1200}",
  "requestContext": { "authorizer": { "jwt": { "claims": { "sub": "51ebc570-f041-70cc-5ac0-79f6177137cb" } } } }
}
```

**rent-renters**: expect `201`:

```json
{
  "routeKey": "POST /api/properties/{id}/renters",
  "pathParameters": { "id": "<propertyId>" },
  "body": "{\"name\": \"Jane Doe\", \"email\": \"jane@example.com\", \"phone\": \"555-123-4567\", \"contactType\": \"primary\"}",
  "requestContext": { "authorizer": { "jwt": { "claims": { "sub": "51ebc570-f041-70cc-5ac0-79f6177137cb" } } } }
}
```

**rent-payments**: expect `201` with `renterName`:

```json
{
  "routeKey": "POST /api/properties/{id}/payments",
  "pathParameters": { "id": "<propertyId>" },
  "body": "{\"amount\": 1200, \"month\": \"2026-09\", \"paidOn\": \"2026-09-03\", \"method\": \"Zelle\", \"renterId\": \"<renterId>\"}",
  "requestContext": { "authorizer": { "jwt": { "claims": { "sub": "51ebc570-f041-70cc-5ac0-79f6177137cb" } } } }
}
```

**rent-dashboard**: expect `200`:

```json
{
  "routeKey": "GET /api/dashboard",
  "queryStringParameters": { "month": "2026-10" },
  "requestContext": { "authorizer": { "jwt": { "claims": { "sub": "51ebc570-f041-70cc-5ac0-79f6177137cb" } } } }
}
```

If a test returns `500`, open the CloudWatch logs link under the result. `AccessDeniedException` means the IAM policy is missing or has the wrong ARN; `KeyError: 'TABLE_NAME'` means the environment variable wasn't saved.

---

## Step 6: API Gateway

### 6.1 Create the HTTP API

1. **API Gateway → Create API → HTTP API → Build.**
2. Add an integration: Lambda → `rent-properties` (or skip integrations here and add them in 6.3).
3. API name: `rent-tracker-api`.
4. Routes: add them in 6.2 (the wizard can create the Properties routes now).
5. Stage: `$default` with **auto-deploy on**. Create.
6. Note the **Invoke URL**.

Check **Deploy → Stages → $default → Automatic deployment: enabled**. If it's off, new routes stay in draft and return `{"message":"Not Found"}` until you click **Deploy**.

### 6.2 Routes (17)

Create each under **Develop → Routes → Create**. Enter only the method and path; no query strings. Parameter names are case-sensitive and must match exactly.

| # | Method | Path | Integration |
| --- | --- | --- | --- |
| 1 | GET | `/api/properties` | rent-properties |
| 2 | POST | `/api/properties` | rent-properties |
| 3 | GET | `/api/properties/{id}` | rent-properties |
| 4 | PUT | `/api/properties/{id}` | rent-properties |
| 5 | DELETE | `/api/properties/{id}` | rent-properties |
| 6 | GET | `/api/properties/{id}/renters` | rent-renters |
| 7 | POST | `/api/properties/{id}/renters` | rent-renters |
| 8 | GET | `/api/properties/{id}/renters/{renterId}` | rent-renters |
| 9 | PUT | `/api/properties/{id}/renters/{renterId}` | rent-renters |
| 10 | DELETE | `/api/properties/{id}/renters/{renterId}` | rent-renters |
| 11 | GET | `/api/properties/{id}/payments` | rent-payments |
| 12 | POST | `/api/properties/{id}/payments` | rent-payments |
| 13 | GET | `/api/properties/{id}/payments/{paymentId}` | rent-payments |
| 14 | PUT | `/api/properties/{id}/payments/{paymentId}` | rent-payments |
| 15 | DELETE | `/api/properties/{id}/payments/{paymentId}` | rent-payments |
| 16 | GET | `/api/dashboard` | rent-dashboard |
| 17 | GET | `/api/dashboard/properties/{id}` | rent-dashboard |

The property's parameter is always `{id}` at the same position in every path.

### 6.3 Integrations (one per function)

**Develop → Integrations → Attach integrations to routes:**

1. Select the first route of a function → **Create and attach an integration**:
   - Integration type: **Lambda function**
   - Region `us-east-2`, function `rent-<name>`
   - Advanced: payload format version **2.0** (the code depends on it), timeout 30000 ms
   - **Grant API Gateway permission to invoke your Lambda function: on**
2. For that function's other routes, choose it from **Choose an existing integration** → **Attach integration**.

Result: 4 integrations, each attached to its function's routes. (The create wizard may make one integration per route; that works but is untidy.)

### 6.4 JWT authorizer

**Develop → Authorization → Manage authorizers → Create** (or **Attach authorization → Create and attach an authorizer** on a route):

| Field | Value |
| --- | --- |
| Type | JWT |
| Name | `cognito` |
| Identity source | `$request.header.Authorization` |
| Issuer URL | `https://cognito-idp.us-east-2.amazonaws.com/us-east-2_buHZ4Y9vJ` |
| Audience | `4fss6ia5mf1iuj2bj1q0jq0ncs` (the app client ID) |

Then **Attach authorizers to routes**: attach `cognito` to **all 17 routes**. Every route must show **JWT Auth**; a route without it is open to the internet.

Cognito access tokens carry the client ID in `client_id` rather than `aud`; the authorizer checks that claim when `aud` is absent.

### 6.5 CORS

**Develop → CORS → Configure:**

| Setting | Value |
| --- | --- |
| Access-Control-Allow-Origin | `http://localhost:5173` (add the S3/CloudFront URL later; never `*`) |
| Access-Control-Allow-Headers | `authorization` and `content-type`, **added as two separate entries** |
| Access-Control-Allow-Methods | GET, POST, PUT, DELETE, OPTIONS |
| Access-Control-Expose-Headers | none |
| Access-Control-Max-Age | 300 |
| Access-Control-Allow-Credentials | NO |

API Gateway answers preflight `OPTIONS` requests itself; don't add OPTIONS routes. When CORS is configured on the API, API Gateway ignores CORS headers from Lambda, so the functions don't send any.

### 6.6 Verify the setup from the CLI

```bash
aws apigatewayv2 get-routes --api-id xd30d9fz0c --region us-east-2 \
  --query "Items[].[RouteKey,Target,AuthorizationType]" --output table
# 17 rows, each with integrations/<id> and JWT

aws apigatewayv2 get-stages --api-id xd30d9fz0c --region us-east-2 \
  --query "Items[].[StageName,AutoDeploy]" --output table
# $default  True
```

---

## Step 7: Test everything

Paste into bash (WSL/Ubuntu). Set your email first.

```bash
CLIENT="4fss6ia5mf1iuj2bj1q0jq0ncs"
EMAIL="your-email"
PROFILE="krishrent-dev"
API="https://xd30d9fz0c.execute-api.us-east-2.amazonaws.com"

TOKEN=$(aws cognito-idp initiate-auth --client-id "$CLIENT" --auth-flow USER_PASSWORD_AUTH \
  --auth-parameters USERNAME="$EMAIL",PASSWORD='Test-Passw0rd!' \
  --query "AuthenticationResult.AccessToken" --output text --region us-east-2 --profile "$PROFILE")
H="Authorization: Bearer $TOKEN"
J="Content-Type: application/json"

echo "=== Auth: a missing token is rejected (expect 401 twice)"
for p in properties dashboard; do curl -s -i "$API/api/$p" | head -1; done

echo "=== Properties"
PID=$(curl -s -X POST "$API/api/properties" -H "$H" -H "$J" \
  -d '{"address":"12 Oak St","monthlyRent":1200}' | jq -r .id); echo "property: $PID"
curl -s "$API/api/properties" -H "$H"; echo
curl -s -X PUT "$API/api/properties/$PID" -H "$H" -H "$J" \
  -d '{"address":"12 Oak Street","monthlyRent":1200}'; echo
curl -s -X POST "$API/api/properties" -H "$H" -H "$J" -d '{"address":""}'; echo      # 400

echo "=== Renters"
curl -s -i "$API/api/properties/$PID/renters" | head -1                              # 401
RID=$(curl -s -X POST "$API/api/properties/$PID/renters" -H "$H" -H "$J" \
  -d '{"name":"Jane Doe","email":"jane@example.com","phone":"555-123-4567","contactType":"primary"}' | jq -r .id)
R2=$(curl -s -X POST "$API/api/properties/$PID/renters" -H "$H" -H "$J" \
  -d '{"name":"John Doe","phone":"555-987-6543","contactType":"secondary"}' | jq -r .id)
curl -s "$API/api/properties/$PID/renters" -H "$H"; echo                             # primary first
curl -s -X PUT "$API/api/properties/$PID/renters/$R2" -H "$H" -H "$J" \
  -d '{"name":"John Doe","email":"john@example.com","phone":"555-987-6543","contactType":"secondary"}'; echo
curl -s -X POST "$API/api/properties/$PID/renters" -H "$H" -H "$J" \
  -d '{"name":"X","email":"not-an-email"}'; echo                                     # 400
curl -s -i -X DELETE "$API/api/properties/$PID/renters/$R2" -H "$H" | head -1        # 204

echo "=== Payments"
curl -s -i "$API/api/properties/$PID/payments" | head -1                             # 401
curl -s -X POST "$API/api/properties/$PID/payments" -H "$H" -H "$J" \
  -d "{\"amount\":1200,\"month\":\"2026-09\",\"paidOn\":\"2026-09-03\",\"method\":\"Zelle\",\"renterId\":\"$RID\"}"; echo
curl -s -X POST "$API/api/properties/$PID/payments" -H "$H" -H "$J" \
  -d '{"amount":600.50,"month":"2026-10","paidOn":"2026-10-01","method":"Check"}'; echo
PAY=$(curl -s -X POST "$API/api/properties/$PID/payments" -H "$H" -H "$J" \
  -d '{"amount":599.50,"month":"2026-10","note":"rest of October"}' | jq -r .id)
curl -s "$API/api/properties/$PID/payments?month=2026-10" -H "$H"; echo              # 2 payments
curl -s -X PUT "$API/api/properties/$PID/payments/$PAY" -H "$H" -H "$J" \
  -d '{"amount":599.50,"month":"2026-11"}'; echo                                     # same id, Nov
curl -s -X POST "$API/api/properties/$PID/payments" -H "$H" -H "$J" \
  -d '{"amount":-5,"month":"Sept"}'; echo                                            # 400
curl -s -i -X DELETE "$API/api/properties/$PID/payments/$PAY" -H "$H" | head -1      # 204

echo "=== Dashboard"
curl -s "$API/api/dashboard?month=2026-09" -H "$H" | jq '.properties[] | {address, status, collected, outstanding}'
#   paid, 1200, 0
curl -s "$API/api/dashboard?month=2026-10" -H "$H" | jq '{totals, counts}'
#   partial: collected 600.5, outstanding 599.5
curl -s "$API/api/dashboard/properties/$PID?months=3" -H "$H" | jq '.months[] | {month, status, collected}'

echo "=== Cleanup (optional): deleting the property removes its renters and payments"
# curl -s -i -X DELETE "$API/api/properties/$PID" -H "$H" | head -1                  # 204
```

**Verified results (2026-09-27/28):** every call above returned the expected status; September showed `paid` ($1,200), October `partial` ($600.50 collected, $599.50 outstanding), and the no-token calls returned 401.

---

## Troubleshooting

### What each error means

| Response | Came from | Fix |
| --- | --- | --- |
| `401 {"message":"Unauthorized"}` | Authorizer | Token missing, expired (60 min) or from another client. Refresh `TOKEN` **and** re-set `H`. Check issuer and audience. |
| `200` with no token | A route with no authorizer | Attach `cognito` to it |
| `404 {"message":"Not Found"}` | API Gateway: no matching live route | Route missing, no integration attached, not deployed, or a path typo |
| `{"message":"No route for ..."}` | The Lambda | Route points at the wrong function's integration |
| `{"message":"Internal Server Error"}` (capital S) | API Gateway couldn't invoke Lambda | Turn on the integration's invoke permission |
| `{"message":"Internal server error"}` | The function | Read its CloudWatch logs |
| `{"message":"Property not found"}` | The function | Wrong id, or the property belongs to another user |
| `jq` prints `null` for every field | The body is an error message | Run the same `curl` without `jq` to see it |

### Gotchas hit during the build

| Symptom | Cause | Fix |
| --- | --- | --- |
| `aws configure sso` → `InvalidRequestException ... RegisterClient` | SSO region ≠ Identity Center's region | Use **us-east-1** for SSO region; `us-east-2` is the default client region |
| Portal asks for a username | It's the Identity Center username, not the root email | Find it under Identity Center → Users |
| Account page error "accountId ... length less than or equal to 12" | Clicked an OU's name in Identity Center's account list | Expand the OU with ▶ and click the account |
| "No accounts" after CLI sign-in | User not assigned to the account | Assign user + permission set to the account (Step 1.3) |
| `SignUp is not permitted for this user pool` | Self-registration is off | Create users as admin (Step 3.3) |
| `initiate-auth` returns no token | Console-created user has a temporary password | `admin-set-user-password --permanent` |
| `cognito-idp: command not found` | `TOKEN=aws ...` in bash | `TOKEN=$(aws ...)` |
| 401s after refreshing the token | `H` still holds the old token | Re-run `H="Authorization: Bearer $TOKEN"` |
| Five `rent-properties` integrations | Wizard creates one per route | Harmless; reuse one integration per function going forward |
| New routes return `Not Found` | No integration attached, or not deployed | Attach integration; Deploy or enable auto-deploy |
| Browser CORS failures with `authorization,content-type` as one header | Console treats each entry as one header name | Add `authorization` and `content-type` separately |
| Lambda 128 MB, ~98 MB used | Default memory | 256 MB, 10 s timeout |

---

## Teardown

Delete in this order (reverse of creation). Everything is in the Dev account and us-east-2 unless noted.

1. **API Gateway:** APIs → `rent-tracker-api` → Delete. (Removes routes, integrations, authorizer, stage.)
2. **Lambda:** delete `rent-properties`, `rent-renters`, `rent-payments`, `rent-dashboard`.
3. **CloudWatch Logs:** delete log groups `/aws/lambda/rent-*`.
4. **IAM:** delete role `rent-tracker-lambda-role` (its inline policy goes with it).
5. **Cognito:** user pool → Settings → turn **deletion protection off** → Delete user pool. (Removes users, app client and domain.)
6. **DynamoDB:** table → Additional settings → turn **deletion protection off** → Delete table. Optionally create an on-demand backup first. Point-in-time recovery stops with the table.
7. **Budget** (management account): delete it if the account is going away.
8. **Account (only if retiring it entirely):** management account → Organizations → the account → Close. Closure has a 90-day post-closure period.

CLI equivalent for steps 1–6:

```bash
R=us-east-2
aws apigatewayv2 delete-api --api-id xd30d9fz0c --region $R
for f in rent-properties rent-renters rent-payments rent-dashboard; do
  aws lambda delete-function --function-name $f --region $R
  aws logs delete-log-group --log-group-name /aws/lambda/$f --region $R 2>/dev/null
done
aws iam delete-role-policy --role-name rent-tracker-lambda-role --policy-name rent-tracker-dynamodb
aws iam detach-role-policy --role-name rent-tracker-lambda-role \
  --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole
aws iam delete-role --role-name rent-tracker-lambda-role
aws cognito-idp update-user-pool --user-pool-id us-east-2_buHZ4Y9vJ --deletion-protection INACTIVE --region $R
aws cognito-idp delete-user-pool --user-pool-id us-east-2_buHZ4Y9vJ --region $R
aws dynamodb update-table --table-name RentTracker --no-deletion-protection-enabled --region $R
aws dynamodb delete-table --table-name RentTracker --region $R
```

`update-user-pool` resets any settings you don't pass, which is fine right before a delete but not otherwise.

---

## What's next

1. **React frontend:** replace the old login with Cognito (e.g. `react-oidc-context`, authorization code + PKCE), send the **access token** as `Authorization: Bearer`, switch to the nested renters/payments paths, add the monthly rent field.
2. **Host on S3 (+ CloudFront):** then add the site URL to the Cognito callback and sign-out URLs and to API Gateway's CORS origins; turn off `ALLOW_USER_PASSWORD_AUTH`.
3. **Automate:** rebuild all of this as infrastructure as code (SAM, CDK or Terraform) so IT and Prod are one command each.
4. **Possible improvements:** a read-only role for the dashboard; rent history per property (the dashboard currently judges past months against today's rent); a "tracking since" date so months before a tenancy aren't shown as unpaid.

---

## Appendix A: API reference

All routes require `Authorization: Bearer <Cognito access token>`. Bodies are JSON. Money is returned as a number.

### Properties

| Method | Path | Body | Success |
| --- | --- | --- | --- |
| GET | `/api/properties` | | 200, list sorted by address |
| POST | `/api/properties` | `{"address": "12 Oak St", "monthlyRent": 1200}` | 201 |
| GET | `/api/properties/{id}` | | 200 |
| PUT | `/api/properties/{id}` | same as POST (full replace; omitting `monthlyRent` clears it) | 200 |
| DELETE | `/api/properties/{id}` | | 204, also deletes its renters and payments |

Rules: `address` required, ≤ 300 chars. `monthlyRent` optional, ≥ 0, ≤ 1,000,000, at most 2 decimals.

### Renters

| Method | Path | Body | Success |
| --- | --- | --- | --- |
| GET | `/api/properties/{id}/renters` | | 200, primary contacts first |
| POST | `/api/properties/{id}/renters` | `{"name": "Jane Doe", "email": "jane@example.com", "phone": "555-123-4567", "contactType": "primary"}` | 201 |
| GET | `/api/properties/{id}/renters/{renterId}` | | 200 |
| PUT | `/api/properties/{id}/renters/{renterId}` | same as POST (full replace) | 200 |
| DELETE | `/api/properties/{id}/renters/{renterId}` | | 204 |

Rules: `name` required, ≤ 120 chars; `email` optional, valid format, stored lowercase; `phone` optional, digits and `+ ( ) - .` and spaces, 7–25 chars; `contactType` `primary` (default) or `secondary`.

### Payments

| Method | Path | Body | Success |
| --- | --- | --- | --- |
| GET | `/api/properties/{id}/payments[?month=YYYY-MM]` | | 200, newest month first |
| POST | `/api/properties/{id}/payments` | `{"amount": 1200, "month": "2026-09", "paidOn": "2026-09-03", "method": "Zelle", "renterId": "...", "note": "..."}` | 201 |
| GET | `/api/properties/{id}/payments/{paymentId}` | | 200 |
| PUT | `/api/properties/{id}/payments/{paymentId}` | same as POST (full replace; changing `month` keeps the id) | 200 |
| DELETE | `/api/properties/{id}/payments/{paymentId}` | | 204 |

Rules: `amount` required, > 0, ≤ 1,000,000, at most 2 decimals; `month` required `YYYY-MM`; `paidOn` optional `YYYY-MM-DD`, defaults to today (UTC); `method` ≤ 40 chars; `note` ≤ 500 chars; `renterId` optional but must be a renter of that property (the response then includes `renterName`). Partial payments are simply several payments with the same `month`.

### Dashboard

| Method | Path | Success |
| --- | --- | --- |
| GET | `/api/dashboard[?month=YYYY-MM]` | 200: `month`, `totals` (expected, collected, outstanding), `counts` (paid, partial, unpaid, no-rent-set, properties), `properties[]` (status, collected, outstanding, paymentCount, lastPaidOn, primaryContact), most urgent first |
| GET | `/api/dashboard/properties/{id}[?months=1..36]` | 200: `months[]` newest first (default 12), each with expected, collected, outstanding, status, paymentCount |

Status: `paid` (collected ≥ monthlyRent), `partial`, `unpaid`, or `no-rent-set`. The month defaults to the current UTC month. Past months use the property's current rent.

### Errors

`400` validation (`{"message": "..."}`), `401` no or bad token, `404` not found or another user's data, `500` internal (details in CloudWatch).

---

## Appendix B: rent-properties

Paste as `lambda_function.py` in the `rent-properties` function, then **Deploy**.

```python
"""
Properties service for the rent tracker, running on AWS Lambda.

Routes (API Gateway HTTP API, payload format 2.0):
  GET    /api/properties          list the signed-in user's properties
  POST   /api/properties          create a property      body: {"address": "...", "monthlyRent": 1200}
  GET    /api/properties/{id}     get one property
  PUT    /api/properties/{id}     update a property      body: {"address": "...", "monthlyRent": 1200}
  DELETE /api/properties/{id}     delete a property and its renters and payments

monthlyRent is optional (a number >= 0, at most 2 decimals). The dashboard uses
it to tell full from partial payments. PUT replaces both fields, so leaving
monthlyRent out of a PUT clears it.

The user comes from the Cognito JWT that API Gateway has already validated:
event.requestContext.authorizer.jwt.claims.sub

DynamoDB single-table layout (table name in env var TABLE_NAME):
  Property : PK = USER#<sub>                          SK = PROPERTY#<propertyId>
  Renter   : PK = USER#<sub>#PROPERTY#<propertyId>    SK = RENTER#<renterId>
  Payment  : PK = USER#<sub>#PROPERTY#<propertyId>    SK = PAYMENT#<yyyy-mm>#<paymentId>
Everything belonging to a property shares one partition key, so deleting a
property is one query plus a batch delete.
"""

import base64
import json
import os
import uuid
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

TABLE_NAME = os.environ["TABLE_NAME"]  # fail fast if it isn't configured

table = boto3.resource("dynamodb").Table(TABLE_NAME)


# ---------- helpers ----------

# CORS is configured once on the API Gateway HTTP API (allowed origins are
# your site's exact URLs). API Gateway adds the CORS headers itself, so the
# function returns none.
def respond(status, body=None):
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json"},
        "body": "" if body is None else json.dumps(body, default=str),
    }


def get_user_id(event):
    try:
        return event["requestContext"]["authorizer"]["jwt"]["claims"]["sub"]
    except (KeyError, TypeError):
        return None


def parse_body(event):
    raw = event.get("body") or "{}"
    if event.get("isBase64Encoded"):
        raw = base64.b64decode(raw).decode("utf-8")
    try:
        data = json.loads(raw, parse_float=Decimal)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def now():
    return datetime.now(timezone.utc).isoformat()


def to_property(item):
    rent = item.get("monthlyRent")
    return {
        "id": item["id"],
        "address": item["address"],
        "monthlyRent": float(rent) if rent is not None else None,
        "createdAt": item.get("createdAt"),
        "updatedAt": item.get("updatedAt"),
    }


MAX_RENT = Decimal("1000000")
CENT = Decimal("0.01")


def validate_property(data):
    """Returns ((address, monthly_rent_or_None), error_message)."""
    if data is None:
        return None, "Request body must be a JSON object"
    address = str(data.get("address") or "").strip()
    if not address:
        return None, "address is required"
    if len(address) > 300:
        return None, "address must be 300 characters or fewer"

    raw_rent = data.get("monthlyRent")
    if raw_rent is None or (isinstance(raw_rent, str) and not raw_rent.strip()):
        return (address, None), None
    if isinstance(raw_rent, bool):
        return None, "monthlyRent must be a number"
    try:
        rent = Decimal(str(raw_rent).strip())
    except InvalidOperation:
        return None, "monthlyRent must be a number"
    if not rent.is_finite() or rent < 0:
        return None, "monthlyRent must be 0 or more"
    if rent > MAX_RENT:
        return None, "monthlyRent is too large"
    if rent != rent.quantize(CENT):
        return None, "monthlyRent can have at most 2 decimal places"
    return (address, rent.quantize(CENT)), None


# ---------- route handlers ----------

def list_properties(user):
    items = []
    kwargs = {
        "KeyConditionExpression": Key("PK").eq(f"USER#{user}")
        & Key("SK").begins_with("PROPERTY#")
    }
    while True:
        page = table.query(**kwargs)
        items.extend(page["Items"])
        if "LastEvaluatedKey" not in page:
            break
        kwargs["ExclusiveStartKey"] = page["LastEvaluatedKey"]
    props = sorted((to_property(i) for i in items), key=lambda p: p["address"].lower())
    return respond(200, props)


def create_property(user, event):
    fields, error = validate_property(parse_body(event))
    if error:
        return respond(400, {"message": error})
    address, rent = fields
    prop_id = str(uuid.uuid4())
    ts = now()
    item = {
        "PK": f"USER#{user}",
        "SK": f"PROPERTY#{prop_id}",
        "type": "property",
        "id": prop_id,
        "address": address,
        "createdAt": ts,
        "updatedAt": ts,
    }
    if rent is not None:
        item["monthlyRent"] = rent
    table.put_item(Item=item)
    return respond(201, to_property(item))


def get_property(user, prop_id):
    item = table.get_item(Key={"PK": f"USER#{user}", "SK": f"PROPERTY#{prop_id}"}).get("Item")
    if not item:
        return respond(404, {"message": "Property not found"})
    return respond(200, to_property(item))


def update_property(user, prop_id, event):
    fields, error = validate_property(parse_body(event))
    if error:
        return respond(400, {"message": error})
    address, rent = fields
    values = {":a": address, ":u": now()}
    if rent is None:
        update = "SET address = :a, updatedAt = :u REMOVE monthlyRent"
    else:
        update = "SET address = :a, monthlyRent = :r, updatedAt = :u"
        values[":r"] = rent
    try:
        result = table.update_item(
            Key={"PK": f"USER#{user}", "SK": f"PROPERTY#{prop_id}"},
            UpdateExpression=update,
            ConditionExpression="attribute_exists(PK)",
            ExpressionAttributeValues=values,
            ReturnValues="ALL_NEW",
        )
    except ClientError as e:
        if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
            return respond(404, {"message": "Property not found"})
        raise
    return respond(200, to_property(result["Attributes"]))


def delete_property(user, prop_id):
    key = {"PK": f"USER#{user}", "SK": f"PROPERTY#{prop_id}"}
    if "Item" not in table.get_item(Key=key):
        return respond(404, {"message": "Property not found"})

    # Remove the property's renters and payments (they share one partition).
    kwargs = {
        "KeyConditionExpression": Key("PK").eq(f"USER#{user}#PROPERTY#{prop_id}"),
        "ProjectionExpression": "PK, SK",
    }
    with table.batch_writer() as batch:
        while True:
            page = table.query(**kwargs)
            for child in page["Items"]:
                batch.delete_item(Key={"PK": child["PK"], "SK": child["SK"]})
            if "LastEvaluatedKey" not in page:
                break
            kwargs["ExclusiveStartKey"] = page["LastEvaluatedKey"]

    table.delete_item(Key=key)
    return respond(204)


# ---------- entry point ----------

def lambda_handler(event, context):
    user = get_user_id(event)
    if not user:
        return respond(401, {"message": "Unauthorized"})

    route = event.get("routeKey", "")
    prop_id = (event.get("pathParameters") or {}).get("id")

    try:
        if route == "GET /api/properties":
            return list_properties(user)
        if route == "POST /api/properties":
            return create_property(user, event)
        if route == "GET /api/properties/{id}":
            return get_property(user, prop_id)
        if route == "PUT /api/properties/{id}":
            return update_property(user, prop_id, event)
        if route == "DELETE /api/properties/{id}":
            return delete_property(user, prop_id)
        return respond(404, {"message": f"No route for {route}"})
    except Exception as e:  # log the detail, return a generic error
        print(f"ERROR handling {route}: {e!r}")
        return respond(500, {"message": "Internal server error"})
```

---

## Appendix C: rent-renters

Paste as `lambda_function.py` in the `rent-renters` function, then **Deploy**.

```python
"""
Renters service for the rent tracker, running on AWS Lambda.

Routes (API Gateway HTTP API, payload format 2.0). Renters always belong to a
property, so the property id is part of the path:
  GET    /api/properties/{id}/renters               list a property's renters
  POST   /api/properties/{id}/renters               add a renter
  GET    /api/properties/{id}/renters/{renterId}    get one renter
  PUT    /api/properties/{id}/renters/{renterId}    update a renter
  DELETE /api/properties/{id}/renters/{renterId}    remove a renter

Renter body:
  {"name": "Jane Doe", "email": "jane@example.com", "phone": "555-123-4567",
   "contactType": "primary" | "secondary"}
name is required; email and phone are optional; contactType defaults to primary.

The user comes from the Cognito JWT that API Gateway has already validated:
event.requestContext.authorizer.jwt.claims.sub

DynamoDB single-table layout (table name in env var TABLE_NAME):
  Property : PK = USER#<sub>                          SK = PROPERTY#<propertyId>
  Renter   : PK = USER#<sub>#PROPERTY#<propertyId>    SK = RENTER#<renterId>
"""

import base64
import json
import os
import re
import uuid
from datetime import datetime, timezone

import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

TABLE_NAME = os.environ["TABLE_NAME"]  # fail fast if it isn't configured

table = boto3.resource("dynamodb").Table(TABLE_NAME)

CONTACT_TYPES = ("primary", "secondary")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PHONE_RE = re.compile(r"^[0-9+()\-.\s]{7,25}$")


# ---------- helpers ----------

# CORS is handled by API Gateway, so the function returns no CORS headers.
def respond(status, body=None):
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json"},
        "body": "" if body is None else json.dumps(body, default=str),
    }


def get_user_id(event):
    try:
        return event["requestContext"]["authorizer"]["jwt"]["claims"]["sub"]
    except (KeyError, TypeError):
        return None


def parse_body(event):
    raw = event.get("body") or "{}"
    if event.get("isBase64Encoded"):
        raw = base64.b64decode(raw).decode("utf-8")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def now():
    return datetime.now(timezone.utc).isoformat()


def renter_pk(user, prop_id):
    return f"USER#{user}#PROPERTY#{prop_id}"


def property_exists(user, prop_id):
    item = table.get_item(
        Key={"PK": f"USER#{user}", "SK": f"PROPERTY#{prop_id}"},
        ProjectionExpression="PK",
    ).get("Item")
    return item is not None


def to_renter(item):
    return {
        "id": item["id"],
        "propertyId": item["propertyId"],
        "name": item["name"],
        "email": item.get("email", ""),
        "phone": item.get("phone", ""),
        "contactType": item.get("contactType", "primary"),
        "createdAt": item.get("createdAt"),
        "updatedAt": item.get("updatedAt"),
    }


def validate_renter(data):
    """Returns (clean_fields, error_message)."""
    if data is None:
        return None, "Request body must be a JSON object"

    name = str(data.get("name") or "").strip()
    email = str(data.get("email") or "").strip().lower()
    phone = str(data.get("phone") or "").strip()
    contact_type = str(data.get("contactType") or "primary").strip().lower()

    if not name:
        return None, "name is required"
    if len(name) > 120:
        return None, "name must be 120 characters or fewer"
    if email and (len(email) > 254 or not EMAIL_RE.match(email)):
        return None, "email is not a valid email address"
    if phone and not PHONE_RE.match(phone):
        return None, "phone may contain only digits, spaces and + ( ) - ."
    if contact_type not in CONTACT_TYPES:
        return None, "contactType must be 'primary' or 'secondary'"

    return {"name": name, "email": email, "phone": phone, "contactType": contact_type}, None


# ---------- route handlers ----------

def list_renters(user, prop_id):
    if not property_exists(user, prop_id):
        return respond(404, {"message": "Property not found"})
    items = []
    kwargs = {
        "KeyConditionExpression": Key("PK").eq(renter_pk(user, prop_id))
        & Key("SK").begins_with("RENTER#")
    }
    while True:
        page = table.query(**kwargs)
        items.extend(page["Items"])
        if "LastEvaluatedKey" not in page:
            break
        kwargs["ExclusiveStartKey"] = page["LastEvaluatedKey"]
    renters = [to_renter(i) for i in items]
    # Primary contacts first, then alphabetical by name.
    renters.sort(key=lambda r: (r["contactType"] != "primary", r["name"].lower()))
    return respond(200, renters)


def create_renter(user, prop_id, event):
    fields, error = validate_renter(parse_body(event))
    if error:
        return respond(400, {"message": error})
    if not property_exists(user, prop_id):
        return respond(404, {"message": "Property not found"})

    renter_id = str(uuid.uuid4())
    ts = now()
    item = {
        "PK": renter_pk(user, prop_id),
        "SK": f"RENTER#{renter_id}",
        "type": "renter",
        "id": renter_id,
        "propertyId": prop_id,
        **fields,
        "createdAt": ts,
        "updatedAt": ts,
    }
    table.put_item(Item=item)
    return respond(201, to_renter(item))


def get_renter(user, prop_id, renter_id):
    item = table.get_item(
        Key={"PK": renter_pk(user, prop_id), "SK": f"RENTER#{renter_id}"}
    ).get("Item")
    if not item:
        return respond(404, {"message": "Renter not found"})
    return respond(200, to_renter(item))


def update_renter(user, prop_id, renter_id, event):
    fields, error = validate_renter(parse_body(event))
    if error:
        return respond(400, {"message": error})
    try:
        result = table.update_item(
            Key={"PK": renter_pk(user, prop_id), "SK": f"RENTER#{renter_id}"},
            UpdateExpression=(
                "SET #n = :n, email = :e, phone = :p, contactType = :c, updatedAt = :u"
            ),
            ConditionExpression="attribute_exists(PK)",
            ExpressionAttributeNames={"#n": "name"},  # "name" is a DynamoDB reserved word
            ExpressionAttributeValues={
                ":n": fields["name"],
                ":e": fields["email"],
                ":p": fields["phone"],
                ":c": fields["contactType"],
                ":u": now(),
            },
            ReturnValues="ALL_NEW",
        )
    except ClientError as e:
        if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
            return respond(404, {"message": "Renter not found"})
        raise
    return respond(200, to_renter(result["Attributes"]))


def delete_renter(user, prop_id, renter_id):
    try:
        table.delete_item(
            Key={"PK": renter_pk(user, prop_id), "SK": f"RENTER#{renter_id}"},
            ConditionExpression="attribute_exists(PK)",
        )
    except ClientError as e:
        if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
            return respond(404, {"message": "Renter not found"})
        raise
    return respond(204)


# ---------- entry point ----------

def lambda_handler(event, context):
    user = get_user_id(event)
    if not user:
        return respond(401, {"message": "Unauthorized"})

    route = event.get("routeKey", "")
    params = event.get("pathParameters") or {}
    prop_id = params.get("id")
    renter_id = params.get("renterId")

    try:
        if route == "GET /api/properties/{id}/renters":
            return list_renters(user, prop_id)
        if route == "POST /api/properties/{id}/renters":
            return create_renter(user, prop_id, event)
        if route == "GET /api/properties/{id}/renters/{renterId}":
            return get_renter(user, prop_id, renter_id)
        if route == "PUT /api/properties/{id}/renters/{renterId}":
            return update_renter(user, prop_id, renter_id, event)
        if route == "DELETE /api/properties/{id}/renters/{renterId}":
            return delete_renter(user, prop_id, renter_id)
        return respond(404, {"message": f"No route for {route}"})
    except Exception as e:  # log the detail, return a generic error
        print(f"ERROR handling {route}: {e!r}")
        return respond(500, {"message": "Internal server error"})
```

---

## Appendix D: rent-payments

Paste as `lambda_function.py` in the `rent-payments` function, then **Deploy**.

```python
"""
Payments service for the rent tracker, running on AWS Lambda.

Routes (API Gateway HTTP API, payload format 2.0). Payments belong to a
property, so the property id is part of the path:
  GET    /api/properties/{id}/payments                 list payments (optional ?month=YYYY-MM)
  POST   /api/properties/{id}/payments                 record a payment
  GET    /api/properties/{id}/payments/{paymentId}     get one payment
  PUT    /api/properties/{id}/payments/{paymentId}     update a payment
  DELETE /api/properties/{id}/payments/{paymentId}     delete a payment

Payment body:
  {"amount": 1200.00,          required, > 0, at most 2 decimal places
   "month": "2026-09",         required, the rent month this payment counts toward
   "paidOn": "2026-09-03",     optional, defaults to today (UTC)
   "method": "Zelle",          optional, free text
   "renterId": "...",          optional, must be a renter of this property
   "note": "..."}              optional
A month can have any number of payments, so partial payments are simply
several payments with the same month.

The user comes from the Cognito JWT that API Gateway has already validated:
event.requestContext.authorizer.jwt.claims.sub

DynamoDB single-table layout (table name in env var TABLE_NAME):
  Property : PK = USER#<sub>                          SK = PROPERTY#<propertyId>
  Renter   : PK = USER#<sub>#PROPERTY#<propertyId>    SK = RENTER#<renterId>
  Payment  : PK = USER#<sub>#PROPERTY#<propertyId>    SK = PAYMENT#<yyyy-mm>#<paymentId>
Putting the month in the sort key lets one query fetch a single month's payments.
"""

import base64
import json
import os
import re
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation

import boto3
from boto3.dynamodb.conditions import Attr, Key

TABLE_NAME = os.environ["TABLE_NAME"]  # fail fast if it isn't configured

table = boto3.resource("dynamodb").Table(TABLE_NAME)
# The resource's client converts Python values to DynamoDB types itself,
# so transactions below can pass plain dicts.
client = table.meta.client

MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
MAX_AMOUNT = Decimal("1000000")
CENT = Decimal("0.01")


# ---------- helpers ----------

# CORS is handled by API Gateway, so the function returns no CORS headers.
def respond(status, body=None):
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json"},
        "body": "" if body is None else json.dumps(body, default=str),
    }


def get_user_id(event):
    try:
        return event["requestContext"]["authorizer"]["jwt"]["claims"]["sub"]
    except (KeyError, TypeError):
        return None


def parse_body(event):
    raw = event.get("body") or "{}"
    if event.get("isBase64Encoded"):
        raw = base64.b64decode(raw).decode("utf-8")
    try:
        data = json.loads(raw, parse_float=Decimal)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def now():
    return datetime.now(timezone.utc).isoformat()


def child_pk(user, prop_id):
    return f"USER#{user}#PROPERTY#{prop_id}"


def payment_sk(month, payment_id):
    return f"PAYMENT#{month}#{payment_id}"


def property_exists(user, prop_id):
    item = table.get_item(
        Key={"PK": f"USER#{user}", "SK": f"PROPERTY#{prop_id}"},
        ProjectionExpression="PK",
    ).get("Item")
    return item is not None


def get_renter_name(user, prop_id, renter_id):
    item = table.get_item(
        Key={"PK": child_pk(user, prop_id), "SK": f"RENTER#{renter_id}"},
        ProjectionExpression="#n",
        ExpressionAttributeNames={"#n": "name"},
    ).get("Item")
    return item["name"] if item else None


def query_all(**kwargs):
    items = []
    while True:
        page = table.query(**kwargs)
        items.extend(page["Items"])
        if "LastEvaluatedKey" not in page:
            return items
        kwargs["ExclusiveStartKey"] = page["LastEvaluatedKey"]


def find_payment(user, prop_id, payment_id):
    """The month is part of the sort key, so look the payment up by its id."""
    items = query_all(
        KeyConditionExpression=Key("PK").eq(child_pk(user, prop_id))
        & Key("SK").begins_with("PAYMENT#"),
        FilterExpression=Attr("id").eq(payment_id),
    )
    return items[0] if items else None


def to_payment(item):
    return {
        "id": item["id"],
        "propertyId": item["propertyId"],
        "amount": float(item["amount"]),
        "month": item["month"],
        "paidOn": item["paidOn"],
        "method": item.get("method", ""),
        "renterId": item.get("renterId", ""),
        "renterName": item.get("renterName", ""),
        "note": item.get("note", ""),
        "createdAt": item.get("createdAt"),
        "updatedAt": item.get("updatedAt"),
    }


def validate_payment(data):
    """Returns (clean_fields, error_message)."""
    if data is None:
        return None, "Request body must be a JSON object"

    raw_amount = data.get("amount")
    if raw_amount is None or isinstance(raw_amount, bool):
        return None, "amount is required"
    try:
        amount = Decimal(str(raw_amount).strip())
    except InvalidOperation:
        return None, "amount must be a number"
    if not amount.is_finite() or amount <= 0:
        return None, "amount must be greater than 0"
    if amount > MAX_AMOUNT:
        return None, "amount is too large"
    if amount != amount.quantize(CENT):
        return None, "amount can have at most 2 decimal places"
    amount = amount.quantize(CENT)

    month = str(data.get("month") or "").strip()
    if not MONTH_RE.match(month):
        return None, "month is required, in the form YYYY-MM"

    paid_on = str(data.get("paidOn") or "").strip() or date.today().isoformat()
    try:
        datetime.strptime(paid_on, "%Y-%m-%d")
    except ValueError:
        return None, "paidOn must be a date in the form YYYY-MM-DD"

    method = str(data.get("method") or "").strip()
    if len(method) > 40:
        return None, "method must be 40 characters or fewer"
    note = str(data.get("note") or "").strip()
    if len(note) > 500:
        return None, "note must be 500 characters or fewer"
    renter_id = str(data.get("renterId") or "").strip()

    return {
        "amount": amount,
        "month": month,
        "paidOn": paid_on,
        "method": method,
        "note": note,
        "renterId": renter_id,
    }, None


def build_item(user, prop_id, payment_id, fields, renter_name, created_at):
    item = {
        "PK": child_pk(user, prop_id),
        "SK": payment_sk(fields["month"], payment_id),
        "type": "payment",
        "id": payment_id,
        "propertyId": prop_id,
        "amount": fields["amount"],
        "month": fields["month"],
        "paidOn": fields["paidOn"],
        "createdAt": created_at,
        "updatedAt": now(),
    }
    # DynamoDB doesn't need empty optional attributes; leave them off.
    for key in ("method", "note", "renterId"):
        if fields[key]:
            item[key] = fields[key]
    if renter_name:
        item["renterName"] = renter_name
    return item


def resolve_renter(user, prop_id, fields):
    """Returns (renter_name, error_response)."""
    if not fields["renterId"]:
        return None, None
    name = get_renter_name(user, prop_id, fields["renterId"])
    if name is None:
        return None, respond(400, {"message": "renterId is not a renter of this property"})
    return name, None


# ---------- route handlers ----------

def list_payments(user, prop_id, event):
    if not property_exists(user, prop_id):
        return respond(404, {"message": "Property not found"})

    month = ((event.get("queryStringParameters") or {}).get("month") or "").strip()
    if month and not MONTH_RE.match(month):
        return respond(400, {"message": "month must be in the form YYYY-MM"})
    prefix = f"PAYMENT#{month}#" if month else "PAYMENT#"

    items = query_all(
        KeyConditionExpression=Key("PK").eq(child_pk(user, prop_id))
        & Key("SK").begins_with(prefix)
    )
    payments = [to_payment(i) for i in items]
    # Newest rent month first, then most recent payment date first.
    payments.sort(key=lambda p: (p["month"], p["paidOn"], p["createdAt"] or ""), reverse=True)
    return respond(200, payments)


def create_payment(user, prop_id, event):
    fields, error = validate_payment(parse_body(event))
    if error:
        return respond(400, {"message": error})
    if not property_exists(user, prop_id):
        return respond(404, {"message": "Property not found"})
    renter_name, err = resolve_renter(user, prop_id, fields)
    if err:
        return err

    item = build_item(user, prop_id, str(uuid.uuid4()), fields, renter_name, now())
    table.put_item(Item=item)
    return respond(201, to_payment(item))


def get_payment(user, prop_id, payment_id):
    item = find_payment(user, prop_id, payment_id)
    if not item:
        return respond(404, {"message": "Payment not found"})
    return respond(200, to_payment(item))


def update_payment(user, prop_id, payment_id, event):
    fields, error = validate_payment(parse_body(event))
    if error:
        return respond(400, {"message": error})
    existing = find_payment(user, prop_id, payment_id)
    if not existing:
        return respond(404, {"message": "Payment not found"})
    renter_name, err = resolve_renter(user, prop_id, fields)
    if err:
        return err

    item = build_item(user, prop_id, payment_id, fields, renter_name, existing.get("createdAt"))

    if item["SK"] == existing["SK"]:
        table.put_item(Item=item)  # same month: replace in place
    else:
        # The month is part of the key, so moving a payment to another month
        # means writing the new item and deleting the old one, atomically.
        client.transact_write_items(TransactItems=[
            {"Put": {
                "TableName": TABLE_NAME,
                "Item": item,
            }},
            {"Delete": {
                "TableName": TABLE_NAME,
                "Key": {"PK": existing["PK"], "SK": existing["SK"]},
            }},
        ])
    return respond(200, to_payment(item))


def delete_payment(user, prop_id, payment_id):
    existing = find_payment(user, prop_id, payment_id)
    if not existing:
        return respond(404, {"message": "Payment not found"})
    table.delete_item(Key={"PK": existing["PK"], "SK": existing["SK"]})
    return respond(204)


# ---------- entry point ----------

def lambda_handler(event, context):
    user = get_user_id(event)
    if not user:
        return respond(401, {"message": "Unauthorized"})

    route = event.get("routeKey", "")
    params = event.get("pathParameters") or {}
    prop_id = params.get("id")
    payment_id = params.get("paymentId")

    try:
        if route == "GET /api/properties/{id}/payments":
            return list_payments(user, prop_id, event)
        if route == "POST /api/properties/{id}/payments":
            return create_payment(user, prop_id, event)
        if route == "GET /api/properties/{id}/payments/{paymentId}":
            return get_payment(user, prop_id, payment_id)
        if route == "PUT /api/properties/{id}/payments/{paymentId}":
            return update_payment(user, prop_id, payment_id, event)
        if route == "DELETE /api/properties/{id}/payments/{paymentId}":
            return delete_payment(user, prop_id, payment_id)
        return respond(404, {"message": f"No route for {route}"})
    except Exception as e:  # log the detail, return a generic error
        print(f"ERROR handling {route}: {e!r}")
        return respond(500, {"message": "Internal server error"})
```

---

## Appendix E: rent-dashboard

Paste as `lambda_function.py` in the `rent-dashboard` function, then **Deploy**.

```python
"""
Dashboard service for the rent tracker, running on AWS Lambda. Read-only.

Routes (API Gateway HTTP API, payload format 2.0):
  GET /api/dashboard?month=YYYY-MM
      Rent status of every property for one month (default: the current month).
  GET /api/dashboard/properties/{id}?months=12
      One property's month-by-month history, newest first (default 12, max 36).

Status per property and month:
  paid        collected >= monthlyRent
  partial     0 < collected < monthlyRent
  unpaid      nothing collected yet
  no-rent-set the property has no monthlyRent, so paid/partial can't be judged
Past months are compared with the property's current monthlyRent.

The user comes from the Cognito JWT that API Gateway has already validated:
event.requestContext.authorizer.jwt.claims.sub

Reads the single table written by the other services (env var TABLE_NAME):
  Property : PK = USER#<sub>                          SK = PROPERTY#<propertyId>
  Renter   : PK = USER#<sub>#PROPERTY#<propertyId>    SK = RENTER#<renterId>
  Payment  : PK = USER#<sub>#PROPERTY#<propertyId>    SK = PAYMENT#<yyyy-mm>#<paymentId>
"""

import json
import os
import re
from datetime import datetime, timezone
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Key

TABLE_NAME = os.environ["TABLE_NAME"]  # fail fast if it isn't configured

table = boto3.resource("dynamodb").Table(TABLE_NAME)

MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
ZERO = Decimal("0")


# ---------- helpers ----------

# CORS is handled by API Gateway, so the function returns no CORS headers.
def respond(status, body=None):
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json"},
        "body": "" if body is None else json.dumps(body, default=str),
    }


def get_user_id(event):
    try:
        return event["requestContext"]["authorizer"]["jwt"]["claims"]["sub"]
    except (KeyError, TypeError):
        return None


def current_month():
    return datetime.now(timezone.utc).strftime("%Y-%m")


def previous_months(end_month, count):
    """[end_month, the month before, ...], count items, newest first."""
    year, month = (int(x) for x in end_month.split("-"))
    months = []
    for _ in range(count):
        months.append(f"{year:04d}-{month:02d}")
        month -= 1
        if month == 0:
            year, month = year - 1, 12
    return months


def money(value):
    return float(value) if value is not None else None


def query_all(**kwargs):
    items = []
    while True:
        page = table.query(**kwargs)
        items.extend(page["Items"])
        if "LastEvaluatedKey" not in page:
            return items
        kwargs["ExclusiveStartKey"] = page["LastEvaluatedKey"]


def list_properties(user):
    return query_all(
        KeyConditionExpression=Key("PK").eq(f"USER#{user}") & Key("SK").begins_with("PROPERTY#")
    )


def child_items(user, prop_id, sk_prefix):
    return query_all(
        KeyConditionExpression=Key("PK").eq(f"USER#{user}#PROPERTY#{prop_id}")
        & Key("SK").begins_with(sk_prefix)
    )


def status_for(rent, collected):
    if rent is None:
        return "no-rent-set"
    if collected <= ZERO:
        return "unpaid" if rent > ZERO else "paid"
    return "paid" if collected >= rent else "partial"


def month_summary(rent, collected):
    return {
        "expected": money(rent),
        "collected": money(collected),
        "outstanding": money(max(rent - collected, ZERO)) if rent is not None else None,
        "status": status_for(rent, collected),
    }


def primary_contact(renters):
    if not renters:
        return None
    renters = sorted(
        renters, key=lambda r: (r.get("contactType") != "primary", r.get("name", "").lower())
    )
    r = renters[0]
    return {"name": r.get("name", ""), "email": r.get("email", ""), "phone": r.get("phone", "")}


# ---------- route handlers ----------

def month_overview(user, event):
    month = ((event.get("queryStringParameters") or {}).get("month") or "").strip() or current_month()
    if not MONTH_RE.match(month):
        return respond(400, {"message": "month must be in the form YYYY-MM"})

    rows = []
    totals = {"expected": ZERO, "collected": ZERO, "outstanding": ZERO}
    counts = {"paid": 0, "partial": 0, "unpaid": 0, "no-rent-set": 0}

    for prop in list_properties(user):
        prop_id = prop["id"]
        rent = prop.get("monthlyRent")
        payments = child_items(user, prop_id, f"PAYMENT#{month}#")
        renters = child_items(user, prop_id, "RENTER#")
        collected = sum((p["amount"] for p in payments), ZERO)

        summary = month_summary(rent, collected)
        counts[summary["status"]] += 1
        totals["collected"] += collected
        if rent is not None:
            totals["expected"] += rent
            totals["outstanding"] += max(rent - collected, ZERO)

        rows.append({
            "propertyId": prop_id,
            "address": prop["address"],
            "monthlyRent": money(rent),
            **summary,
            "paymentCount": len(payments),
            "lastPaidOn": max((p["paidOn"] for p in payments), default=None),
            "primaryContact": primary_contact(renters),
        })

    # Most urgent first: unpaid, partial, no rent set, paid; then by address.
    order = {"unpaid": 0, "partial": 1, "no-rent-set": 2, "paid": 3}
    rows.sort(key=lambda r: (order[r["status"]], r["address"].lower()))

    return respond(200, {
        "month": month,
        "totals": {k: money(v) for k, v in totals.items()},
        "counts": {**counts, "properties": len(rows)},
        "properties": rows,
    })


def property_history(user, prop_id, event):
    prop = table.get_item(Key={"PK": f"USER#{user}", "SK": f"PROPERTY#{prop_id}"}).get("Item")
    if not prop:
        return respond(404, {"message": "Property not found"})

    raw = ((event.get("queryStringParameters") or {}).get("months") or "12").strip()
    if not raw.isdigit() or not 1 <= int(raw) <= 36:
        return respond(400, {"message": "months must be a whole number from 1 to 36"})
    months = previous_months(current_month(), int(raw))

    # One query for all of the property's payments, grouped by month in code.
    by_month = {}
    for p in child_items(user, prop_id, "PAYMENT#"):
        by_month.setdefault(p["month"], []).append(p)

    rent = prop.get("monthlyRent")
    history = []
    for m in months:
        payments = by_month.get(m, [])
        collected = sum((p["amount"] for p in payments), ZERO)
        history.append({"month": m, **month_summary(rent, collected), "paymentCount": len(payments)})

    return respond(200, {
        "propertyId": prop_id,
        "address": prop["address"],
        "monthlyRent": money(rent),
        "months": history,
    })


# ---------- entry point ----------

def lambda_handler(event, context):
    user = get_user_id(event)
    if not user:
        return respond(401, {"message": "Unauthorized"})

    route = event.get("routeKey", "")
    prop_id = (event.get("pathParameters") or {}).get("id")

    try:
        if route == "GET /api/dashboard":
            return month_overview(user, event)
        if route == "GET /api/dashboard/properties/{id}":
            return property_history(user, prop_id, event)
        return respond(404, {"message": f"No route for {route}"})
    except Exception as e:  # log the detail, return a generic error
        print(f"ERROR handling {route}: {e!r}")
        return respond(500, {"message": "Internal server error"})
```
