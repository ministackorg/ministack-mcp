# Testing with MiniStack

## pytest patterns

### Fixture: MiniStack endpoint

```python
import pytest
import boto3

@pytest.fixture(scope="session")
def ministack_endpoint():
    return "http://localhost:4566"

@pytest.fixture(autouse=True)
def reset_ministack(ministack_endpoint):
    """Reset MiniStack state before each test."""
    import requests
    requests.post(f"{ministack_endpoint}/_ministack/reset")
    yield

@pytest.fixture
def s3_client(ministack_endpoint):
    return boto3.client("s3", endpoint_url=ministack_endpoint)

@pytest.fixture
def dynamodb_client(ministack_endpoint):
    return boto3.client("dynamodb", endpoint_url=ministack_endpoint)
```

### Example test

```python
def test_s3_roundtrip(s3_client):
    s3_client.create_bucket(Bucket="test-bucket")
    s3_client.put_object(Bucket="test-bucket", Key="hello.txt", Body=b"world")
    obj = s3_client.get_object(Bucket="test-bucket", Key="hello.txt")
    assert obj["Body"].read() == b"world"
```

## CI/CD integration

### GitHub Actions

```yaml
services:
  ministack:
    image: ministackorg/ministack:latest
    ports:
      - 4566:4566
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock

steps:
  - uses: actions/checkout@v4
  - name: Wait for MiniStack
    run: |
      for i in $(seq 1 30); do
        curl -sf http://localhost:4566/_ministack/health && break
        sleep 1
      done
  - name: Run tests
    env:
      AWS_ENDPOINT_URL: http://localhost:4566
    run: pytest
```

### GitLab CI

```yaml
services:
  - name: ministackorg/ministack:latest
    alias: ministack

variables:
  AWS_ENDPOINT_URL: http://ministack:4566

test:
  script:
    - pytest
```

## Test isolation

- Use `autouse=True` reset fixture for full isolation between tests.
- For faster tests, reset only the services you use:
  ```python
  s3_client.delete_bucket(Bucket="test-bucket")
  ```
- Use unique resource names per test to allow parallel execution without reset.

## Waiting for Docker-backed services

RDS and ECS start real containers. Poll until ready:

```python
import time

def wait_for_rds(client, db_id, timeout=60):
    deadline = time.time() + timeout
    while time.time() < deadline:
        resp = client.describe_db_instances(DBInstanceIdentifier=db_id)
        status = resp["DBInstances"][0]["DBInstanceStatus"]
        if status == "available":
            return resp["DBInstances"][0]
        time.sleep(2)
    raise TimeoutError(f"RDS {db_id} not available after {timeout}s")
```
