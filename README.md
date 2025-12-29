# CI/CD

## Elevator pitch
Gated CI validates packaging, tests, linting, security; builds and tags Docker images with a deterministic version (ticgen). Tag → prerelease → automated PR into landing-zone → bot approval & auto-merge (optional) → Kubernetes deploy using a reusable k8s template with rollout verification and rollback.

---

## CI (ci.yml) — Key jobs
- Trigger: pull_request (all branches)
- Runner/container: internal runner `self-hosted` + python image `amr-registry...python:3.11.9`
- validate-pyproject: `poetry check` (quick schema validation)
- checks:
  - `poetry install`, `tox -e unit-test`, `python -m build`
  - install package from `dist/` and run: black, bandit, mypy, pylint, isort
  - many checks use `if: always()` to surface results even on prior failure
- versions: run shared `ticgen` action to compute `tic` and `version` outputs (used across build/publish)
- run-build: reusable workflow (`build.yml`) that runs `./malilap plan generate` and uploads build artifacts
- publish: Docker buildx, login to internal ACR, push image tagged with computed version
- required-ci-check: enforces all required jobs succeed before merging; uploads summary artifact

Artifacts & versioning
- Builds uploaded as artifacts (e.g., `dist-nix`)
- Versions computed with `ticgen` from `pyproject.toml` → deterministic image tags

---

## CD (cd.yml + create-prerelease.yml + pre-release.yml + prod-release.yml)
- create-prerelease.yml: turns any pushed tag into a GitHub prerelease (API call)
- pre-release.yml (on prereleased):
  - Validates release origin (must be automated)
  - Checks out `actions.malilap.deploy` action and runs the composite action (which executes `auto_deploy.py`)
  - Creates PRs in `applications.psg.malilap-1source.landing-zone` to update k8s env file(s)
- prod-release.yml: triggered on release edits; can run deploy with different flags (skip_merge, no delete)
- Auto flow: tag -> prerelease -> auto PR to landing zone -> checks -> bot approval -> merge -> verify -> optionally convert to official release

---

## Auto-deploy (auto_deploy.py + action.yml) — behavior summary
- Inputs via env prefix `GITHUB_` (pydantic Settings)
- Main steps:
  1. Choose target env file: pre-prod (default) or prod when skip_merge
  2. Read env file from landing-zone repo, update `export IMAGE_VERSION=...` to release tag
  3. Create branch `refs/heads/<release_tag>` (upsert if exists) and a PR to `main`
  4. Fetch PR details, sync remote PR check-suite/check-run statuses back to local tag commit (mirrors remote CI)
  5. Monitor check runs until completion; require success
  6. If all checks pass and skip_merge==false:
     - Approve PR using bot token
     - Merge PR (squash default)
     - Wait and verify deployment via HTTP endpoint (polling)
  7. If configured, delete release branch and/or convert prerelease to official release
- action.yml installs `requests`, `malilap-core`, `pydantic-settings` and runs the script inside composite action

---

## K8s deployment (k8s-deploy-template.yml)
- Inputs: env-file path which contains IMAGE_NAME, IMAGE_VERSION, NAME, DEPLOYMENT, DEPLOYMENT_NAME
- Steps:
  - Setup kubectl and write kubeconfig from secret
  - For PR: `kubectl set image` dry-run
  - For push: `kubectl set image`, `kubectl rollout status`, poll until pod RUNNING & image matches
  - On failure: `kubectl rollout undo`, then verify rollback

---

## Security & network
- Tokens/secrets: SYS_PSAS_CICD_GH_PAT, SYS_PSGSW_BOT_GH_PAT, SYS_PSAS_CICD_PASSWORD, KUBECONFIG (kept in GH Secrets)
- Bot token separated from GH token for approval/merge actions
- Corporate proxy & internal PyPI used via env vars (HTTP_PROXY, PIP_EXTRA_INDEX_URL, pip.ini)

---

## Failure handling & observability
- Lint/tests report with `if: always()` for diagnostics
- Auto-deploy: fails if multiple/zero PRs found, fails on failed checks, raises if deployment verification fails
- k8s template: rollback on failure, verifies rollout status
- Artifacts & uploaded summaries aid debugging

---

## Quick risks & proposed fixes
- Race conditions on similarly named tags/branches → add locking or unique branch prefix
- Long polling loops → add max-timeouts & exponential backoff
- Bot token scope → narrow permissions and audit usage
- Docker builds use `no-cache: true` → enable caching for faster builds
- Improve visibility: add metrics, GitHub Checks annotations, longer artifact retention

---

## Two-sentence interview summary
A reproducible, gated CI builds and validates the package and Docker image, using shared actions for versioning and builds. Releases are staged (prerelease) and automatically create PRs in the landing-zone; a bot can approve and merge when remote checks pass and a templated k8s deployment updates and verifies the live cluster with rollback on failure.


# CICD
![image](https://user-images.githubusercontent.com/43002915/147396612-62575bde-85d1-4449-84a8-1a2be4faa897.png)  

![image](https://user-images.githubusercontent.com/43002915/147396623-e5816d19-5ec7-4315-9748-dc09f3010ec5.png)

![image](https://user-images.githubusercontent.com/43002915/147396791-788b1ab6-7965-4b70-8593-61eda0be6a32.png)  

![image](https://user-images.githubusercontent.com/43002915/147396795-fe48bb84-e829-4507-9e37-569c476dcce3.png)
  
![image](https://user-images.githubusercontent.com/43002915/147396807-72247787-5013-4c77-b974-a87250cb6c5c.png)  

Testing Phase / Automated Testing  
![image](https://user-images.githubusercontent.com/43002915/147396820-0ef5d3d5-4f26-445f-ac67-a439e21aa242.png)
  
![image](https://user-images.githubusercontent.com/43002915/147396834-2b9a1210-00ac-4d6e-b8d3-d9b71edc7b8b.png)  

![image](https://user-images.githubusercontent.com/43002915/147396839-5b78187e-a669-4ca8-822b-2bd9b73fd597.png)  

![image](https://user-images.githubusercontent.com/43002915/147396845-77f5a0bd-6752-4d50-99f9-27bb286ac03b.png)  

![image](https://user-images.githubusercontent.com/43002915/147396857-1bfdadfc-8e97-4448-8923-3c45dbfb58ec.png)  

![image](https://user-images.githubusercontent.com/43002915/147396859-2ea8d13e-5994-41ae-a2ae-f1bba1e1594e.png)  

![image](https://user-images.githubusercontent.com/43002915/147396864-c4a4f1a6-2beb-4921-b0e9-b51963e3d71a.png) 

![image](https://user-images.githubusercontent.com/43002915/147396904-d52d5b17-b2d4-4f7f-a4e5-bcc187acf327.png)

![image](https://user-images.githubusercontent.com/43002915/147396916-72d59f15-df5d-4677-9a0e-1adf5e5280cf.png)  

![image](https://user-images.githubusercontent.com/43002915/147396925-fb12d0a9-91b5-41b1-b70e-af578256776e.png)  

![image](https://user-images.githubusercontent.com/43002915/147396947-ef79cc2d-183e-4375-bb67-e75c2d7100aa.png)  

![image](https://user-images.githubusercontent.com/43002915/147396951-195034df-f432-43bd-a2d1-f1c25365393a.png)  

![image](https://user-images.githubusercontent.com/43002915/147396955-260046b3-cee3-48f8-be67-f5c3a6169628.png)  
