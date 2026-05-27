# Migrating from LocalStack to MiniStack

## Overview

MiniStack is a drop-in replacement for most LocalStack Community Edition
workflows. The main changes are endpoint configuration and Docker image name.

## Step 1: Swap the Docker image

```diff
- image: localstack/localstack:latest
+ image: ministackorg/ministack:latest
```

Both use port 4566 by default.

## Step 2: Update endpoint URLs

MiniStack uses the same port convention. If you had:

```
LOCALSTACK_HOSTNAME=localhost
EDGE_PORT=4566
```

Replace with:

```
AWS_ENDPOINT_URL=http://localhost:4566
```

Or set `MINISTACK_ENDPOINT_URL` for MCP tools.

## Step 3: Update SDK configuration

The `endpoint_url` parameter is the same across all SDKs. Just change the
hostname if you were using a LocalStack-specific hostname.

## Step 4: Update Docker Compose

```diff
services:
-  localstack:
-    image: localstack/localstack:latest
+  ministack:
+    image: ministackorg/ministack:latest
     ports:
       - "4566:4566"
     volumes:
       - /var/run/docker.sock:/var/run/docker.sock
```

## Step 5: Update CI configuration

Replace service references in GitHub Actions, GitLab CI, etc.

## Step 6: Remove LocalStack-specific configuration

These LocalStack-specific env vars are NOT used by MiniStack:
- `SERVICES` — MiniStack always starts all services
- `LOCALSTACK_API_KEY` — MiniStack has no Pro tier
- `EDGE_PORT` — use standard port 4566
- `DEFAULT_REGION` — use `AWS_DEFAULT_REGION`
- `LAMBDA_EXECUTOR` — MiniStack always uses Docker for Lambda

## Step 7: Verify

```bash
# Start MiniStack
docker run -d -p 4566:4566 \
  -v /var/run/docker.sock:/var/run/docker.sock \
  ministackorg/ministack:latest

# Check health
curl http://localhost:4566/_ministack/health

# Run your test suite
pytest
```

## Key differences

| Feature | LocalStack CE | MiniStack |
|---------|--------------|-----------|
| Port | 4566 | 4566 |
| Pro tier | Yes | No |
| Lambda | Docker/local | Docker (warm pool) |
| RDS | Stub only (Pro) | Real Postgres/MySQL containers |
| ECS | Stub only | Real Docker containers |
| EKS | Stub only (Pro) | Real k3s containers |
| IAM enforcement | No | No |
| Persistence | Pro feature | `PERSIST_STATE=1` |
| Reset endpoint | `/_localstack/health` | `/_ministack/reset` |

## Terraform

No changes needed to resource definitions. Only the provider endpoint block
needs updating (same URL, same port).
