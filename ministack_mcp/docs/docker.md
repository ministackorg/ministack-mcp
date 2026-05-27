# MiniStack Docker Setup

## Quick start

```bash
docker run -d \
  --name ministack \
  -p 4566:4566 \
  -v /var/run/docker.sock:/var/run/docker.sock \
  ministackorg/ministack:latest
```

## Docker socket

MiniStack needs the Docker socket for services that run real backends:
- **Lambda** — worker containers for function execution
- **RDS** — Postgres/MySQL containers
- **ECS** — task containers
- **EKS** — k3s containers
- **ElastiCache** — Redis/Memcached containers
- **OpenSearch** — OpenSearch containers
- **Glue** — PySpark job containers
- **MWAA** — Airflow containers

Without the socket, these services fall back to stubs or in-memory emulation.

```bash
docker run -d \
  -p 4566:4566 \
  -v /var/run/docker.sock:/var/run/docker.sock \
  ministackorg/ministack:latest
```

## Docker Compose

```yaml
version: "3.8"
services:
  ministack:
    image: ministackorg/ministack:latest
    ports:
      - "4566:4566"
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
    environment:
      - PERSIST_STATE=1          # re-create Docker-backed resources on restart
      - S3_PERSIST=1             # persist S3 objects to disk
      - MINISTACK_DATA_DIR=/data
    volumes:
      - ministack-data:/data

volumes:
  ministack-data:
```

## Persistence

By default MiniStack is ephemeral. Enable persistence with:

- `PERSIST_STATE=1` — re-spawn Docker containers (RDS, ECS, etc.) on boot
- `S3_PERSIST=1` — write S3 objects to disk
- `MINISTACK_DATA_DIR=/data` — base directory for persistent data

## Network

Docker-backed services (RDS, ECS, EKS, ElastiCache) run on a `ministack` Docker network.
Containers can reach each other by name and can reach MiniStack at `host.docker.internal:4566`.

## Resource limits

For CI environments, limit memory:

```bash
docker run -d --memory=2g -p 4566:4566 \
  -v /var/run/docker.sock:/var/run/docker.sock \
  ministackorg/ministack:latest
```
