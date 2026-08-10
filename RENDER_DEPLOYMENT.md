# Render Deployment

The application lives in `research_app/`. Render builds one Docker service that
serves the React UI and the FastAPI endpoints from the same origin.

## First-time setup

1. Push this repository to GitHub.
2. In Render, choose **New > Blueprint** and select this repository.
3. Confirm the `academic-paper-research-agent` service from `render.yaml`.
4. Provide `OPENAI_API_KEY`. `SEMANTIC_SCHOLAR_API_KEY` is optional.
5. Create the Blueprint and wait for `/api/health` to become healthy.

Render initially creates the service with automatic deploys disabled because
deployment is gated by GitHub Actions.

## Connect continuous deployment

1. Open the Render service's **Settings** page and copy its Deploy Hook URL.
2. In GitHub, open **Settings > Secrets and variables > Actions**.
3. Add a repository secret named `RENDER_DEPLOY_HOOK_URL`.
4. Push to `main`.

The `CI and Render Deploy` workflow tests the backend, builds the frontend, and
builds the production Docker image. It calls the secret deploy hook only after
all three jobs pass on `main`. Pull requests run validation without deploying.

## Local production check

```bash
docker build -f research_app/Dockerfile.render -t research-agent:local research_app
docker run --rm -p 10000:10000 \
  -e OPENAI_API_KEY=dummy \
  research-agent:local
```

Open `http://localhost:10000` and check
`http://localhost:10000/api/health`.
