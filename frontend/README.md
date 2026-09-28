# Rent Tracker — front end

React 19 + Vite + Tailwind CSS v4. See the README in the project root for the full setup and the backend services.

```bash
npm install
npm run dev          # http://localhost:5173 (expects the backend gateway on :8080)
```

- **API calls** all go through `src/lib/api.js`. In development, Vite forwards `/api/*` to `http://localhost:8080`. To point it somewhere else, set `API_URL=http://host:port npm run dev`.
- **Styling** lives in `src/index.css` as named classes (`btn`, `card`, `input`, `badge-paid`, and so on). Components only use those names.
- **Sign-in** stores the JWT from the auth service in localStorage. Any 401 response sends you back to the sign-in page.

## Deploy to S3

```bash
VITE_API_BASE_URL=https://api.your-domain.com npm run build     # outputs dist/
aws s3 sync dist/ s3://your-bucket --delete
```

Leave `VITE_API_BASE_URL` unset if CloudFront serves the API under the same domain at `/api/*`. Links use `/#/...`, so no S3 redirect rules are needed.
