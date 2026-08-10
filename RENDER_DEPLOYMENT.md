# Render Deployment

The application lives in `research_app/`. Render builds one Docker service that
serves the React UI and the FastAPI endpoints from the same origin.

## First-time setup

1. Push this repository to GitHub.
2. In Render, choose **New > Blueprint** and select this repository.
3. Confirm the `academic-paper-research-agent` service from `render.yaml`.
4. Provide `OPENAI_API_KEY`. `SEMANTIC_SCHOLAR_API_KEY` is optional.
5. Create the Blueprint and wait for `/api/health` to become healthy.

Render waits for the repository's CI checks to pass before deploying a commit.

## Continuous deployment

The `CI and Render Deploy` workflow tests the backend, builds the frontend, and
builds the production Docker image. With `autoDeployTrigger: checksPass`, Render
deploys a `main` commit only after those GitHub checks pass. No deploy-hook
secret is required.

For an existing Render service, sync the Blueprint after changing
`render.yaml`, or set **Auto-Deploy** to **After CI Checks Pass** in the service
settings.

## Local production check

```bash
docker build -f research_app/Dockerfile.render -t research-agent:local research_app
docker run --rm -p 10000:10000 \
  -e OPENAI_API_KEY=dummy \
  research-agent:local
```

Open `http://localhost:10000` and check
`http://localhost:10000/api/health`.
