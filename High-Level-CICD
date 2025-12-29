# High-Level CI/CD Overview

In this project, I designed and maintained a fully automated CI/CD pipeline using GitHub Actions, supporting build, test, versioning, containerization, release automation, and Kubernetes deployment for the Lapwing Webhook Listener service.

The pipeline follows enterprise-grade DevOps practices with strong controls around versioning, security, and deployment validation.

---

## CI – Continuous Integration Flow

### 1. Trigger
- Runs on pull requests to any branch.
- Ensures every code change is validated before merge.

### 2. Code Quality & Validation
The CI pipeline performs:
- Poetry dependency validation
- Unit tests via `tox`
- Static analysis:
  - `black` → formatting
  - `isort` → import order
  - `pylint` → code quality score
  - `bandit` → security checks
  - `mypy` → type checking

All checks must pass or the PR fails.

### 3. Build & Package
- Builds the Python package using `poetry build`
- Installs and validates the package
- Creates distributable artifacts
- Uses containerized runners for consistency

### 4. Version Management
- Uses a centralized TIC (Tag & Increment Controller) to:
  - Generate semantic versions
  - Maintain traceability between code, builds, and releases

---

## CD – Continuous Deployment Flow

### 1. Docker Image Build & Push
- Builds a Docker image using a hardened base image
- Pushes the image to a private Artifactory/ACR registry
- Images are tagged using the generated semantic version

### 2. Pre-Release Automation
- When a version tag is created:
  - A GitHub pre-release is automatically generated
  - Metadata and changelogs are attached
  - Triggers the next deployment stage

### 3. Automated Promotion via GitOps
- Deployment logic lives in a separate infrastructure (landing-zone) repo
- A bot automatically:
  - Creates or updates environment-specific config files (env/sh scripts)
  - Opens a PR against the deployment repository
  - Waits for all checks to pass
  - Auto-approves and merges when safe

This ensures full traceability and minimizes manual intervention.

### 4. Kubernetes Deployment
- Uses reusable GitHub workflows for Kubernetes deployment
- Updates image tags in environment manifests
- Performs:
  - Rolling updates
  - Health checks
  - Rollbacks on failure
- Supports pre-prod → prod promotion flow

---

## Security & Governance
- Uses short-lived GitHub tokens and scoped bot tokens
- Secrets stored in GitHub Secrets (no hardcoded credentials)
- Network access controlled via corporate proxy environment variables
- Full audit trail via GitHub Actions runs and PR history

---

## Key Highlights You Can Say in Interviews
- “I designed an end-to-end CI/CD pipeline using GitHub Actions that handles testing, packaging, versioning, Docker builds, and Kubernetes deployment.”
- “The pipeline enforces quality gates, automates releases, and uses GitOps principles for environment promotion.”
- “It supports automated rollouts, rollback safety, and integrates deeply with internal artifact repositories and security policies.”

---
