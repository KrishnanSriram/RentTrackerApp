# Rent Tracker

Track rent across your rental properties. There's a React front end and five small FastAPI services, each in its own Docker container, with data in DynamoDB.

```
Browser (React app, :5173)
   │  every call goes to /api/...
   ▼
Gateway (nginx, :8080)  — routes by path, like an ALB in ECS
   ├─ /api/auth        →  auth         →  table rent-users
   ├─ /api/properties  →  properties   →  table rent-properties
   ├─ /api/renters     →  renters      →  table rent-renters
   ├─ /api/payments    →  payments     →  table rent-payments
   └─ /api/dashboard   →  dashboard    (no table; reads from properties, renters, payments)

Service-to-service calls:
   renters, payments  →  properties         "does this property exist and belong to this user?"
   properties         →  renters, payments  "property deleted; remove its renters and payments"
```

## Code layout

```
docker-compose.yml             runs everything locally, including DynamoDB Local
backend/
  common.py                    shared helpers: DynamoDB access, validation, JWT, service calls
  requirements.txt             one dependency list for all services
  services/<name>/main.py      the whole service: validate(), then the routes
  services/<name>/Dockerfile   one image per service
  gateway/nginx.conf           path routing
  tests/test_api.py            end-to-end API tests
frontend/                      React app (all API calls in src/lib/api.js)
```

There are no schema or model classes. Requests are plain dictionaries. Each service has a `validate(body)` function that checks the fields and returns a clean dict, and that dict is stored in DynamoDB exactly as the API returns it. Invalid input gets a 422 with a readable message, such as `{"detail": "zip is not valid"}`.

## DynamoDB tables

| Table | Partition key | Sort key | Notes |
|---|---|---|---|
| `rent-users` | `email` | | Registration uses a conditional write, so duplicate emails are rejected |
| `rent-properties` | `ownerId` | `id` | |
| `rent-renters` | `ownerId` | `id` | `propertyId` stored as an attribute |
| `rent-payments` | `ownerId` | `id` | `propertyId`, `month` (YYYY-MM) stored as attributes |

Every record is keyed by the owner's user ID, so a user can only ever read or change their own items. Listing a user's records is one `Query` on `ownerId`; filtering by property or month happens in code. That's plenty fast for a personal portfolio. If a user ever has tens of thousands of payments, add a GSI on `ownerId` + `month`.

Locally, each service creates its table on first start. On AWS, tables are not created automatically; see below.

## Run it locally

You need **Docker Desktop** and **Node.js 20.19+**.

```bash
docker compose up --build          # backend + DynamoDB Local
cd frontend && npm install && npm run dev
```

Open http://localhost:5173 and create an account. The Vite dev server forwards `/api/...` to the gateway on port 8080.

- **API docs**, where you can "Authorize" with a token from `/api/auth/login`: http://localhost:8080/api/properties/docs (likewise for `auth`, `renters`, `payments`, `dashboard`)
- **Tests** (while the stack is running): `pip install pytest httpx && pytest backend/tests -v`
- **Look at the data** with the AWS CLI:
  ```bash
  export AWS_ACCESS_KEY_ID=local AWS_SECRET_ACCESS_KEY=local AWS_REGION=us-east-1
  aws dynamodb list-tables --endpoint-url http://localhost:8000
  aws dynamodb scan --table-name rent-properties --endpoint-url http://localhost:8000
  ```
- `docker compose down` stops everything and keeps the data. `docker compose down -v` also deletes the data.

**Moving data from the browser-only version:** there, use Backup → Download backup. Here, use Import / export → Import from file.

## API reference

All endpoints except register, login and health need `Authorization: Bearer <token>`.

```
POST   /api/auth/register             {name, email, password}      → {token, expiresAt, user}
POST   /api/auth/login                {email, password}            → {token, expiresAt, user}
GET    /api/auth/me

GET    /api/properties
POST   /api/properties                {name, street, unit, city, state, zip, monthlyRent}
GET    /api/properties/{id}
PUT    /api/properties/{id}
DELETE /api/properties/{id}           also removes its renters and payments

GET    /api/renters?propertyId=
POST   /api/renters                   {propertyId, name, email, phone, role: primary|secondary}
GET | PUT | DELETE /api/renters/{id}

GET    /api/payments?propertyId=&month=YYYY-MM&fromMonth=&toMonth=
POST   /api/payments                  {propertyId, month, amount, date, method, note}
GET | PUT | DELETE /api/payments/{id}

GET    /api/dashboard?month=YYYY-MM                       totals + one row per property
GET    /api/dashboard/properties/{id}/history?months=12&endMonth=YYYY-MM
GET    /api/<service>/health
```

## Configuration (environment variables)

| Variable | Purpose |
|---|---|
| `TABLE_NAME` | The service's DynamoDB table (auth, properties, renters, payments) |
| `DYNAMODB_ENDPOINT` | Set only locally (`http://dynamodb:8000`). Leave unset on AWS. When set, tables are created automatically. |
| `AWS_REGION` | e.g. `us-east-1` |
| `JWT_SECRET` | Signs and verifies tokens. **Must be the same for every service**, long and random in production. |
| `JWT_TTL_MINUTES` | Token lifetime (default 720 = 12 hours) |
| `PROPERTIES_URL`, `RENTERS_URL`, `PAYMENTS_URL` | Where to reach other services (default `http://<name>:8000`) |
| `CORS_ORIGINS` | Comma-separated browser origins, if the React app is on a different domain from the API |

## Moving to ECS

1. **Tables:** create the four tables above (on-demand capacity, string keys) in the console, the CLI or your IaC. For example:
   ```bash
   aws dynamodb create-table --table-name rent-properties --billing-mode PAY_PER_REQUEST \
     --attribute-definitions AttributeName=ownerId,AttributeType=S AttributeName=id,AttributeType=S \
     --key-schema AttributeName=ownerId,KeyType=HASH AttributeName=id,KeyType=RANGE
   ```
2. **Images:** push each one to ECR. Build from `backend/`: `docker build -f services/renters/Dockerfile -t <ecr-repo>/rent-renters:1.0 .`
3. **Permissions:** give each service's ECS task role access to its own table only (`dynamodb:GetItem`, `PutItem`, `DeleteItem`, `Query`, `BatchWriteItem`). Don't set AWS keys or `DYNAMODB_ENDPOINT`; boto3 picks up the task role automatically. The dashboard needs no DynamoDB access.
4. **Secret:** store `JWT_SECRET` in Secrets Manager and reference it in each task definition.
5. **Routing:** an Application Load Balancer replaces nginx, with one rule per path (`/api/renters*` → renters target group, and so on). Health check: `/api/<service>/health`.
6. **Service-to-service calls:** use ECS Service Connect so `http://properties:8000` works as it does in Compose.
7. **Front end:** build with `VITE_API_BASE_URL=https://your-api-domain` and set `CORS_ORIGINS` to your CloudFront domain. Alternatively, route `/api/*` through CloudFront to the ALB so everything is on one domain.

## Known limits

- Deleting a property removes its renters, then its payments, then the property. If a step fails, retrying the delete finishes the job, but it isn't a single transaction.
- The JWT is kept in the browser's localStorage. No password reset or login rate limiting yet; Amazon Cognito would add both.
