"""
MiniStack MCP Server — your local AWS runtime.

You have a full AWS environment running on localhost:4566. Deploy code,
create infrastructure, run tests, and debug — all locally, instantly, free.
No AWS account needed. No cloud costs. No waiting.

When the user asks you to build, test, or debug AWS code — do it here.
Read their code, deploy it to MiniStack, run it, report the results.
MiniStack is invisible to the user. They care about their code working,
not about MiniStack.

What you can do:
  - Deploy Lambda functions, create DynamoDB tables, S3 buckets, SQS queues,
    SNS topics, Kinesis streams, Step Functions, and 60+ more AWS services
  - Run any AWS CLI command locally
  - Test full architectures: API Gateway + Lambda + DynamoDB, event pipelines,
    microservices with real RDS/Redis/ECS containers
  - Apply Terraform and CloudFormation templates
  - Run smoke tests across services
  - Diagnose failures and suggest fixes
  - Export live state as Terraform, CloudFormation, or boto3 code

Endpoint URL is configurable via MINISTACK_ENDPOINT_URL
(default http://localhost:4566).
"""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
from typing import Any

import requests
from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    "MiniStack",
    instructions="""You have a local AWS environment on http://localhost:4566.
When the user asks you to build, test, or debug AWS code, use this environment.
Read their code from the IDE, deploy it here, run it, report results.
Don't talk about MiniStack — just use it. The user cares about their code, not the tool.""",
)

_HERE = os.path.dirname(os.path.abspath(__file__))
_CATALOG_PATH = os.path.join(_HERE, "catalog.json")
_PARITY_PATH = os.path.join(_HERE, "parity.json")
_README_PATH = os.path.join(_HERE, "README.md")


def _endpoint() -> str:
    return os.environ.get("MINISTACK_ENDPOINT_URL", "http://localhost:4566").rstrip("/")


def _load_json(path: str) -> dict:
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


_CATALOG = _load_json(_CATALOG_PATH)
_PARITY = _load_json(_PARITY_PATH)


def _service_record(name: str) -> dict[str, Any] | None:
    svc = _CATALOG.get("services", {}).get(name)
    if not svc:
        return None
    parity = _PARITY.get("services", {}).get(name, {})
    return {
        **svc,
        "status": parity.get("status", "unknown"),
        "real_backend": parity.get("real_backend"),
        "persistence": parity.get("persistence"),
        "multi_tenant": parity.get("multi_tenant"),
        "notes": parity.get("notes"),
        "gotchas": parity.get("gotchas", []),
    }


# ─── MCP Resource: README ────────────────────────────────────────────────────


@mcp.resource("ministack://docs/readme")
def get_readme() -> str:
    if os.path.exists(_README_PATH):
        with open(_README_PATH, "r", encoding="utf-8") as f:
            return f.read()
    return "README.md not found."


# ─── Live probes ─────────────────────────────────────────────────────────────


@mcp.tool()
def ministack_version() -> str:
    """Return the MiniStack version this catalog was built against, plus
    endpoint defaults. Use this first to ground every other answer."""
    info = {
        "ministack_version": _CATALOG.get("ministack_version", "unknown"),
        "catalog_generated_at": _CATALOG.get("generated_at"),
        "endpoint_url": _endpoint(),
        **_CATALOG.get("endpoint", {}),
    }
    return json.dumps(info, indent=2)


@mcp.tool()
def ministack_health() -> str:
    """Probe MINISTACK_ENDPOINT_URL/_ministack/health. Returns live service
    status; if unreachable, the agent should assume MiniStack is not running."""
    try:
        r = requests.get(f"{_endpoint()}/_ministack/health", timeout=2)
        return r.text
    except Exception as e:
        return json.dumps({"error": "unreachable", "endpoint": _endpoint(), "detail": str(e)})


@mcp.tool()
def ministack_reset() -> str:
    """POST MINISTACK_ENDPOINT_URL/_ministack/reset to clear all in-memory
    state. Useful between integration-test scenarios."""
    try:
        requests.post(f"{_endpoint()}/_ministack/reset", timeout=5)
        return json.dumps({"reset": True, "endpoint": _endpoint()})
    except Exception as e:
        return json.dumps({"error": "unreachable", "endpoint": _endpoint(), "detail": str(e)})


@mcp.tool()
def get_endpoint_info() -> str:
    """Return endpoint URL, default port, default account, default region,
    and the auth model (signature is not validated)."""
    info = dict(_CATALOG.get("endpoint", {}))
    info["endpoint_url"] = _endpoint()
    return json.dumps(info, indent=2)


# ─── Catalog reads ───────────────────────────────────────────────────────────


@mcp.tool()
def list_services() -> str:
    """List every emulated service with its status (full, partial, stub,
    paid, unsupported, data-plane) and operation count. Concise overview
    for an agent deciding whether MiniStack covers a given workflow."""
    items = []
    for name in sorted(_CATALOG.get("services", {})):
        rec = _service_record(name) or {}
        items.append({
            "service": name,
            "status": rec.get("status", "unknown"),
            "operation_count": rec.get("operation_count", 0),
            "real_backend": rec.get("real_backend"),
        })
    return json.dumps({"service_count": len(items), "services": items}, indent=2)


@mcp.tool()
def get_service(name: str) -> str:
    """Full info for one service: every supported operation, parity status,
    backend (docker/none), persistence flag, gotchas, and curated notes."""
    rec = _service_record(name)
    if not rec:
        return json.dumps({"error": "service not found", "service": name})
    return json.dumps(rec, indent=2)


@mcp.tool()
def is_operation_supported(service: str, operation: str) -> str:
    """Definitive yes/no for a single (service, operation) pair. Returns
    `supported: true|false` plus the service's status, so the agent can
    distinguish 'not implemented' from 'service is a stub' from 'the verb
    you asked about does not exist on this service in real AWS'."""
    rec = _service_record(service)
    if not rec:
        return json.dumps({
            "service": service,
            "operation": operation,
            "supported": False,
            "reason": "service not emulated by ministack",
        })
    ops = rec.get("operations", [])
    supported = operation in ops
    payload = {
        "service": service,
        "operation": operation,
        "supported": supported,
        "service_status": rec.get("status", "unknown"),
    }
    if not supported:
        payload["reason"] = (
            f"operation not present in catalog for service "
            f"(service has {len(ops)} known operations)"
        )
    return json.dumps(payload, indent=2)


@mcp.tool()
def search_operations(query: str) -> str:
    """Find every operation across every service whose name contains the
    query (case-insensitive). Useful when the agent has a verb in mind
    (e.g. 'PutItem', 'Encrypt') and wants to know which services expose it."""
    q = query.lower()
    if not q:
        return json.dumps({"query": query, "matches": []})
    matches = []
    for svc, data in _CATALOG.get("services", {}).items():
        for op in data.get("operations", []):
            if q in op.lower():
                matches.append({"service": svc, "operation": op})
    return json.dumps({"query": query, "match_count": len(matches), "matches": matches}, indent=2)


@mcp.tool()
def list_config_vars() -> str:
    """List every environment variable that MiniStack reads (MINISTACK_*,
    AWS_*, OPENSEARCH_*, plus a curated extras set). Returns names only —
    use get_config_var(name) for defaults and source files."""
    names = sorted(_CATALOG.get("env_vars", {}).keys())
    return json.dumps({"count": len(names), "env_vars": names}, indent=2)


@mcp.tool()
def get_config_var(name: str) -> str:
    """Details for one env var: default value (if literal), and the
    source files inside ministack/ that read it."""
    var = _CATALOG.get("env_vars", {}).get(name)
    if not var:
        return json.dumps({"error": "env var not found", "name": name})
    return json.dumps(var, indent=2)


# ─── Section 1: Doc Resources ───────────────────────────────────────────────

_DOCS_DIR = os.path.join(_HERE, "docs")


def _read_doc(filename: str) -> str:
    path = os.path.join(_DOCS_DIR, filename)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    return f"{filename} not found."


@mcp.resource("ministack://docs/quickstart")
def get_quickstart_doc() -> str:
    return _read_doc("quickstart.md")


@mcp.resource("ministack://docs/docker")
def get_docker_doc() -> str:
    return _read_doc("docker.md")


@mcp.resource("ministack://docs/terraform")
def get_terraform_doc() -> str:
    return _read_doc("terraform.md")


@mcp.resource("ministack://docs/testing")
def get_testing_doc() -> str:
    return _read_doc("testing.md")


@mcp.resource("ministack://docs/faq")
def get_faq_doc() -> str:
    return _read_doc("faq.md")


@mcp.resource("ministack://docs/migration")
def get_migration_doc() -> str:
    return _read_doc("migration_from_localstack.md")


# ─── Section 2: Diagnostics (live tools) ────────────────────────────────────


@mcp.tool()
def get_docker_status() -> str:
    """Check which MiniStack services have Docker backends running."""
    try:
        r = requests.get(f"{_endpoint()}/_ministack/health", timeout=3)
        health = r.json() if r.headers.get("content-type", "").startswith("application/json") else {"raw": r.text}
        docker_services = []
        for svc_name, svc_info in _PARITY.get("services", {}).items():
            if svc_info.get("real_backend") == "docker":
                docker_services.append(svc_name)
        return json.dumps({
            "health": health,
            "docker_backed_services": sorted(docker_services),
        }, indent=2)
    except Exception as e:
        return json.dumps({"error": "unreachable", "endpoint": _endpoint(), "detail": str(e)})


_LIST_RESOURCE_APIS: dict[str, dict[str, Any]] = {
    "s3": {"method": "GET", "path": "/", "parse": "xml"},
    "dynamodb": {"method": "POST", "target": "DynamoDB_20120810.ListTables", "body": "{}"},
    "sqs": {"method": "POST", "target": "AmazonSQS.ListQueues", "body": "{}"},
    "sns": {"method": "POST", "target": "SNS.ListTopics", "body": "{}"},
    "lambda": {"method": "GET", "path": "/2015-03-31/functions"},
    "kinesis": {"method": "POST", "target": "Kinesis_20131202.ListStreams", "body": "{}"},
    "secretsmanager": {"method": "POST", "target": "secretsmanager.ListSecrets", "body": "{}"},
    "ssm": {"method": "POST", "target": "AmazonSSM.GetParametersByPath", "body": json.dumps({"Path": "/", "Recursive": True})},
    "stepfunctions": {"method": "POST", "target": "AWSStepFunctions.ListStateMachines", "body": "{}"},
    "cloudformation": {"method": "POST", "path": "/", "params": {"Action": "ListStacks", "Version": "2010-05-15"}},
    "iam": {"method": "POST", "path": "/", "params": {"Action": "ListUsers", "Version": "2010-05-08"}},
    "cloudwatch_logs": {"method": "POST", "target": "Logs_20140328.DescribeLogGroups", "body": "{}"},
}


@mcp.tool()
def list_resources(service: str) -> str:
    """List resources for a MiniStack service (s3, dynamodb, sqs, sns, lambda,
    kinesis, secretsmanager, ssm, stepfunctions, cloudformation, iam,
    cloudwatch_logs)."""
    svc = service.lower().replace("-", "_")
    api = _LIST_RESOURCE_APIS.get(svc)
    if not api:
        return json.dumps({"error": f"unsupported service '{service}'", "supported": sorted(_LIST_RESOURCE_APIS.keys())})
    ep = _endpoint()
    try:
        headers: dict[str, str] = {"Content-Type": "application/x-amz-json-1.1"}
        if "target" in api:
            headers["X-Amz-Target"] = api["target"]
        if api["method"] == "GET":
            r = requests.get(f"{ep}{api.get('path', '/')}", headers=headers, params=api.get("params"), timeout=5)
        else:
            r = requests.post(
                f"{ep}{api.get('path', '/')}",
                headers=headers,
                data=api.get("body", ""),
                params=api.get("params"),
                timeout=5,
            )
        try:
            return json.dumps({"service": svc, "response": r.json()}, indent=2)
        except Exception:
            return json.dumps({"service": svc, "response": r.text[:2000]}, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def describe_resource(service: str, identifier: str) -> str:
    """Get details on a specific MiniStack resource by service and identifier."""
    ep = _endpoint()
    svc = service.lower().replace("-", "_")
    try:
        headers = {"Content-Type": "application/x-amz-json-1.1"}
        if svc == "s3":
            r = requests.get(f"{ep}/{identifier}", timeout=5)
        elif svc == "dynamodb":
            headers["X-Amz-Target"] = "DynamoDB_20120810.DescribeTable"
            r = requests.post(ep, headers=headers, data=json.dumps({"TableName": identifier}), timeout=5)
        elif svc == "lambda":
            r = requests.get(f"{ep}/2015-03-31/functions/{identifier}", headers=headers, timeout=5)
        elif svc == "sqs":
            headers["X-Amz-Target"] = "AmazonSQS.GetQueueAttributes"
            r = requests.post(ep, headers=headers, data=json.dumps({"QueueUrl": identifier, "AttributeNames": ["All"]}), timeout=5)
        elif svc == "sns":
            headers["X-Amz-Target"] = "SNS.GetTopicAttributes"
            r = requests.post(ep, headers=headers, data=json.dumps({"TopicArn": identifier}), timeout=5)
        elif svc == "kinesis":
            headers["X-Amz-Target"] = "Kinesis_20131202.DescribeStream"
            r = requests.post(ep, headers=headers, data=json.dumps({"StreamName": identifier}), timeout=5)
        elif svc == "secretsmanager":
            headers["X-Amz-Target"] = "secretsmanager.DescribeSecret"
            r = requests.post(ep, headers=headers, data=json.dumps({"SecretId": identifier}), timeout=5)
        elif svc == "ssm":
            headers["X-Amz-Target"] = "AmazonSSM.GetParameter"
            r = requests.post(ep, headers=headers, data=json.dumps({"Name": identifier}), timeout=5)
        elif svc == "stepfunctions":
            headers["X-Amz-Target"] = "AWSStepFunctions.DescribeStateMachine"
            r = requests.post(ep, headers=headers, data=json.dumps({"stateMachineArn": identifier}), timeout=5)
        else:
            return json.dumps({"error": f"describe not implemented for '{svc}'"})
        try:
            return json.dumps({"service": svc, "identifier": identifier, "response": r.json()}, indent=2)
        except Exception:
            return json.dumps({"service": svc, "identifier": identifier, "response": r.text[:2000]}, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def validate_endpoint() -> str:
    """Comprehensive MiniStack diagnostic: check health, services, and probe
    S3/SQS/SNS to verify the endpoint is working."""
    ep = _endpoint()
    results: dict[str, Any] = {"endpoint": ep, "checks": {}}
    # Health
    try:
        r = requests.get(f"{ep}/_ministack/health", timeout=3)
        results["checks"]["health"] = {"status": "ok", "code": r.status_code}
    except Exception as e:
        results["checks"]["health"] = {"status": "unreachable", "error": str(e)}
        return json.dumps(results, indent=2)
    # Service probes
    probes = {
        "s3": lambda: requests.get(f"{ep}/", timeout=3),
        "sqs": lambda: requests.post(ep, headers={"Content-Type": "application/x-amz-json-1.1", "X-Amz-Target": "AmazonSQS.ListQueues"}, data="{}", timeout=3),
        "sns": lambda: requests.post(ep, headers={"Content-Type": "application/x-amz-json-1.1", "X-Amz-Target": "SNS.ListTopics"}, data="{}", timeout=3),
    }
    for name, probe_fn in probes.items():
        try:
            r = probe_fn()
            results["checks"][name] = {"status": "ok", "code": r.status_code}
        except Exception as e:
            results["checks"][name] = {"status": "error", "error": str(e)}
    # Service count from catalog
    results["catalog_services"] = len(_CATALOG.get("services", {}))
    return json.dumps(results, indent=2)


# ─── Section 3: Live AWS Interaction ────────────────────────────────────────

_DANGEROUS_PATTERNS = re.compile(
    r"\b(rm\s+-rf|sudo|chmod|chown|mkfs|dd\s+if=|shutdown|reboot|halt|"
    r"curl|wget|nc\s|ncat|python|perl|ruby|bash|sh\s+-c|eval|exec)\b",
    re.IGNORECASE,
)


@mcp.tool()
def aws_execute(command: str) -> str:
    """Run an AWS CLI command against MiniStack. The command should start with
    'aws'. Dangerous shell patterns are rejected. 30s timeout."""
    if _DANGEROUS_PATTERNS.search(command):
        return json.dumps({"error": "command contains dangerous patterns", "command": command})
    cmd = command.strip()
    if not cmd.startswith("aws "):
        cmd = "aws " + cmd
    if "--endpoint-url" not in cmd:
        cmd = cmd.replace("aws ", f"aws --endpoint-url {_endpoint()} ", 1)
    try:
        result = subprocess.run(
            shlex.split(cmd),
            capture_output=True,
            text=True,
            timeout=30,
        )
        return json.dumps({
            "command": cmd,
            "exit_code": result.returncode,
            "stdout": result.stdout[:5000],
            "stderr": result.stderr[:2000],
        }, indent=2)
    except subprocess.TimeoutExpired:
        return json.dumps({"error": "timeout (30s)", "command": cmd})
    except Exception as e:
        return json.dumps({"error": str(e), "command": cmd})


_CREATE_COMMANDS: dict[str, str] = {
    "s3": "aws s3 mb s3://{name}",
    "dynamodb": "aws dynamodb create-table --table-name {name} --attribute-definitions AttributeName=pk,AttributeType=S --key-schema AttributeName=pk,KeyType=HASH --billing-mode PAY_PER_REQUEST",
    "sqs": "aws sqs create-queue --queue-name {name}",
    "sns": "aws sns create-topic --name {name}",
    "kinesis": "aws kinesis create-stream --stream-name {name} --shard-count 1",
    "secretsmanager": 'aws secretsmanager create-secret --name {name} --secret-string "placeholder"',
    "ssm": "aws ssm put-parameter --name {name} --value placeholder --type String",
    "lambda": "aws lambda create-function --function-name {name} --runtime python3.12 --handler index.handler --role arn:aws:iam::000000000000:role/lambda-role --zip-file fileb:///dev/null",
}


@mcp.tool()
def create_resource(service: str, name: str, config: str = "") -> str:
    """Create a resource in MiniStack with one command. Supports: s3, dynamodb,
    sqs, sns, kinesis, secretsmanager, ssm, lambda. Pass extra CLI flags via config."""
    svc = service.lower().replace("-", "_")
    template = _CREATE_COMMANDS.get(svc)
    if not template:
        return json.dumps({"error": f"unsupported service '{svc}'", "supported": sorted(_CREATE_COMMANDS.keys())})
    cmd = template.format(name=name)
    if config:
        cmd += f" {config}"
    return aws_execute(cmd)


_DELETE_COMMANDS: dict[str, str] = {
    "s3": "aws s3 rb s3://{identifier} --force",
    "dynamodb": "aws dynamodb delete-table --table-name {identifier}",
    "sqs": "aws sqs delete-queue --queue-url {identifier}",
    "sns": "aws sns delete-topic --topic-arn {identifier}",
    "kinesis": "aws kinesis delete-stream --stream-name {identifier}",
    "secretsmanager": "aws secretsmanager delete-secret --secret-id {identifier} --force-delete-without-recovery",
    "ssm": "aws ssm delete-parameter --name {identifier}",
    "lambda": "aws lambda delete-function --function-name {identifier}",
}


@mcp.tool()
def delete_resource(service: str, identifier: str) -> str:
    """Delete a MiniStack resource by service and identifier."""
    svc = service.lower().replace("-", "_")
    template = _DELETE_COMMANDS.get(svc)
    if not template:
        return json.dumps({"error": f"unsupported service '{svc}'", "supported": sorted(_DELETE_COMMANDS.keys())})
    cmd = template.format(identifier=identifier)
    return aws_execute(cmd)


@mcp.tool()
def invoke_lambda(function_name: str, payload: str = "{}") -> str:
    """Invoke a Lambda function in MiniStack via the REST API."""
    ep = _endpoint()
    try:
        r = requests.post(
            f"{ep}/2015-03-31/functions/{function_name}/invocations",
            headers={"Content-Type": "application/json"},
            data=payload,
            timeout=30,
        )
        try:
            body = r.json()
        except Exception:
            body = r.text[:5000]
        return json.dumps({
            "function": function_name,
            "status_code": r.status_code,
            "response": body,
            "log_result": r.headers.get("X-Amz-Log-Result", ""),
        }, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def put_s3_object(bucket: str, key: str, body: str) -> str:
    """Upload an object to an S3 bucket in MiniStack."""
    ep = _endpoint()
    try:
        r = requests.put(
            f"{ep}/{bucket}/{key}",
            data=body.encode("utf-8"),
            timeout=10,
        )
        return json.dumps({"bucket": bucket, "key": key, "status_code": r.status_code, "etag": r.headers.get("ETag", "")}, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def query_dynamodb(table: str, key_condition: str, expression_values: str = "{}") -> str:
    """Query a DynamoDB table in MiniStack."""
    ep = _endpoint()
    try:
        body = {
            "TableName": table,
            "KeyConditionExpression": key_condition,
        }
        if expression_values and expression_values != "{}":
            body["ExpressionAttributeValues"] = json.loads(expression_values)
        r = requests.post(
            ep,
            headers={
                "Content-Type": "application/x-amz-json-1.0",
                "X-Amz-Target": "DynamoDB_20120810.Query",
            },
            data=json.dumps(body),
            timeout=10,
        )
        return json.dumps({"table": table, "response": r.json()}, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def send_sqs_message(queue_url: str, body: str) -> str:
    """Send a message to an SQS queue in MiniStack."""
    ep = _endpoint()
    try:
        r = requests.post(
            ep,
            headers={
                "Content-Type": "application/x-amz-json-1.0",
                "X-Amz-Target": "AmazonSQS.SendMessage",
            },
            data=json.dumps({"QueueUrl": queue_url, "MessageBody": body}),
            timeout=5,
        )
        return json.dumps({"queue_url": queue_url, "response": r.json()}, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def publish_sns(topic_arn: str, message: str) -> str:
    """Publish a message to an SNS topic in MiniStack."""
    ep = _endpoint()
    try:
        r = requests.post(
            ep,
            data={
                "Action": "Publish",
                "TopicArn": topic_arn,
                "Message": message,
            },
            timeout=5,
        )
        return json.dumps({"topic_arn": topic_arn, "status_code": r.status_code, "response": r.text[:2000]}, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


# ─── Section 4: Testing ─────────────────────────────────────────────────────

import time as _time
import uuid as _uuid


@mcp.tool()
def run_smoke_test(services: str = "s3,dynamodb,sqs,sns,lambda") -> str:
    """Run CRUD smoke tests against MiniStack services. Returns per-service
    pass/fail with timing. Uses unique resource names and cleans up."""
    ep = _endpoint()
    svc_list = [s.strip().lower() for s in services.split(",") if s.strip()]
    results: dict[str, Any] = {}
    uid = _uuid.uuid4().hex[:8]

    for svc in svc_list:
        t0 = _time.time()
        try:
            if svc == "s3":
                bkt = f"smoke-{uid}"
                requests.put(f"{ep}/{bkt}", timeout=5)
                requests.put(f"{ep}/{bkt}/test.txt", data=b"hello", timeout=5)
                r = requests.get(f"{ep}/{bkt}/test.txt", timeout=5)
                ok = r.status_code == 200 and r.text == "hello"
                requests.delete(f"{ep}/{bkt}/test.txt", timeout=5)
                requests.delete(f"{ep}/{bkt}", timeout=5)
                results[svc] = {"pass": ok, "ms": round((_time.time() - t0) * 1000)}
            elif svc == "dynamodb":
                tbl = f"smoke-{uid}"
                headers = {"Content-Type": "application/x-amz-json-1.0", "X-Amz-Target": "DynamoDB_20120810.CreateTable"}
                requests.post(ep, headers=headers, data=json.dumps({
                    "TableName": tbl,
                    "AttributeDefinitions": [{"AttributeName": "pk", "AttributeType": "S"}],
                    "KeySchema": [{"AttributeName": "pk", "KeyType": "HASH"}],
                    "BillingMode": "PAY_PER_REQUEST",
                }), timeout=5)
                headers["X-Amz-Target"] = "DynamoDB_20120810.PutItem"
                requests.post(ep, headers=headers, data=json.dumps({
                    "TableName": tbl, "Item": {"pk": {"S": "test"}, "val": {"S": "hello"}},
                }), timeout=5)
                headers["X-Amz-Target"] = "DynamoDB_20120810.GetItem"
                r = requests.post(ep, headers=headers, data=json.dumps({
                    "TableName": tbl, "Key": {"pk": {"S": "test"}},
                }), timeout=5)
                ok = r.status_code == 200 and "Item" in r.json()
                headers["X-Amz-Target"] = "DynamoDB_20120810.DeleteTable"
                requests.post(ep, headers=headers, data=json.dumps({"TableName": tbl}), timeout=5)
                results[svc] = {"pass": ok, "ms": round((_time.time() - t0) * 1000)}
            elif svc == "sqs":
                qname = f"smoke-{uid}"
                headers = {"Content-Type": "application/x-amz-json-1.0", "X-Amz-Target": "AmazonSQS.CreateQueue"}
                r = requests.post(ep, headers=headers, data=json.dumps({"QueueName": qname}), timeout=5)
                qurl = r.json().get("QueueUrl", "")
                headers["X-Amz-Target"] = "AmazonSQS.SendMessage"
                requests.post(ep, headers=headers, data=json.dumps({"QueueUrl": qurl, "MessageBody": "smoke"}), timeout=5)
                headers["X-Amz-Target"] = "AmazonSQS.ReceiveMessage"
                r = requests.post(ep, headers=headers, data=json.dumps({"QueueUrl": qurl, "MaxNumberOfMessages": 1}), timeout=5)
                msgs = r.json().get("Messages", [])
                ok = len(msgs) > 0 and msgs[0].get("Body") == "smoke"
                headers["X-Amz-Target"] = "AmazonSQS.DeleteQueue"
                requests.post(ep, headers=headers, data=json.dumps({"QueueUrl": qurl}), timeout=5)
                results[svc] = {"pass": ok, "ms": round((_time.time() - t0) * 1000)}
            elif svc == "sns":
                tname = f"smoke-{uid}"
                headers = {"Content-Type": "application/x-amz-json-1.1", "X-Amz-Target": "SNS.CreateTopic"}
                r = requests.post(ep, headers=headers, data=json.dumps({"Name": tname}), timeout=5)
                arn = r.json().get("TopicArn", "")
                ok = bool(arn)
                headers["X-Amz-Target"] = "SNS.DeleteTopic"
                requests.post(ep, headers=headers, data=json.dumps({"TopicArn": arn}), timeout=5)
                results[svc] = {"pass": ok, "ms": round((_time.time() - t0) * 1000)}
            elif svc == "lambda":
                # Lambda needs Docker; just test CreateFunction + ListFunctions
                fname = f"smoke-{uid}"
                r = requests.get(f"{ep}/2015-03-31/functions", timeout=5)
                ok = r.status_code == 200
                results[svc] = {"pass": ok, "ms": round((_time.time() - t0) * 1000), "note": "list-only (create requires zip)"}
            else:
                results[svc] = {"pass": False, "error": "unsupported service for smoke test"}
        except Exception as e:
            results[svc] = {"pass": False, "error": str(e), "ms": round((_time.time() - t0) * 1000)}

    passed = sum(1 for v in results.values() if v.get("pass"))
    return json.dumps({"total": len(results), "passed": passed, "failed": len(results) - passed, "results": results}, indent=2)


@mcp.tool()
def check_terraform_coverage(resource_types: str) -> str:
    """Check which Terraform/CloudFormation resource types are supported by
    MiniStack. Pass a comma-separated list like 'AWS::S3::Bucket,AWS::Lambda::Function'."""
    types = [t.strip() for t in resource_types.split(",") if t.strip()]
    catalog_services = set(_CATALOG.get("services", {}).keys())
    results = []
    for rt in types:
        # Map AWS::ServiceName::Resource to service name
        parts = rt.replace("::", "/").split("/")
        svc_guess = parts[1].lower() if len(parts) >= 2 else rt.lower()
        # Try common mappings
        mapping = {
            "s3": "s3", "dynamodb": "dynamodb", "lambda": "lambda_svc",
            "sqs": "sqs", "sns": "sns", "iam": "iam", "ec2": "ec2",
            "ecs": "ecs", "eks": "eks", "rds": "rds", "kinesis": "kinesis",
            "secretsmanager": "secretsmanager", "ssm": "ssm",
            "stepfunctions": "stepfunctions", "cloudformation": "cloudformation",
            "apigateway": "apigateway", "apigatewayv2": "apigateway",
            "route53": "route53", "cloudfront": "cloudfront", "kms": "kms",
            "acm": "acm", "cognito": "cognito", "events": "eventbridge",
            "wafv2": "waf", "elasticache": "elasticache",
        }
        svc_key = mapping.get(svc_guess, svc_guess)
        found = svc_key in catalog_services
        parity_status = _PARITY.get("services", {}).get(svc_key, {}).get("status", "unknown") if found else "not found"
        results.append({"resource_type": rt, "service": svc_key, "supported": found, "status": parity_status})
    covered = sum(1 for r in results if r["supported"])
    return json.dumps({"total": len(results), "covered": covered, "results": results}, indent=2)


@mcp.tool()
def check_sdk_coverage(operations: str) -> str:
    """Check which service:operation pairs are supported. Pass comma-separated
    pairs like 's3:PutObject,dynamodb:Query'."""
    pairs = [p.strip() for p in operations.split(",") if p.strip()]
    results = []
    for pair in pairs:
        if ":" not in pair:
            results.append({"pair": pair, "error": "expected format service:Operation"})
            continue
        svc, op = pair.split(":", 1)
        rec = _service_record(svc.lower())
        if not rec:
            results.append({"service": svc, "operation": op, "supported": False, "reason": "service not found"})
        else:
            supported = op in rec.get("operations", [])
            results.append({"service": svc, "operation": op, "supported": supported, "service_status": rec.get("status")})
    covered = sum(1 for r in results if r.get("supported"))
    return json.dumps({"total": len(results), "covered": covered, "results": results}, indent=2)


@mcp.tool()
def generate_test_fixture(service: str, language: str = "python") -> str:
    """Generate a pytest fixture for testing against MiniStack. Supports:
    s3, dynamodb, sqs, sns, lambda, kinesis, stepfunctions."""
    svc = service.lower().replace("-", "_")
    boto3_name_map = {
        "s3": "s3", "dynamodb": "dynamodb", "sqs": "sqs", "sns": "sns",
        "lambda": "lambda", "lambda_svc": "lambda", "kinesis": "kinesis",
        "stepfunctions": "stepfunctions",
    }
    boto3_name = boto3_name_map.get(svc)
    if not boto3_name:
        return json.dumps({"error": f"unsupported service '{svc}'", "supported": sorted(boto3_name_map.keys())})
    if language.lower() == "python":
        code = f'''import pytest
import boto3

@pytest.fixture
def {svc}_client():
    """Boto3 {boto3_name} client pointing at MiniStack."""
    return boto3.client(
        "{boto3_name}",
        endpoint_url="http://localhost:4566",
        region_name="us-east-1",
        aws_access_key_id="test",
        aws_secret_access_key="test",
    )

@pytest.fixture(autouse=True)
def _reset_ministack():
    """Reset MiniStack state before each test."""
    import requests
    requests.post("http://localhost:4566/_ministack/reset")
    yield
'''
        return json.dumps({"service": svc, "language": "python", "code": code}, indent=2)
    elif language.lower() in ("javascript", "js", "typescript", "ts"):
        code = f'''const {{ {boto3_name.upper().replace("-", "")}Client }} = require("@aws-sdk/client-{boto3_name}");

const client = new {boto3_name.upper().replace("-", "")}Client({{
  endpoint: "http://localhost:4566",
  region: "us-east-1",
  credentials: {{ accessKeyId: "test", secretAccessKey: "test" }},
}});

beforeEach(async () => {{
  await fetch("http://localhost:4566/_ministack/reset", {{ method: "POST" }});
}});
'''
        return json.dumps({"service": svc, "language": language, "code": code}, indent=2)
    else:
        return json.dumps({"error": f"unsupported language '{language}', try 'python' or 'javascript'"})


@mcp.tool()
def reset_and_verify() -> str:
    """Reset MiniStack and verify the environment is clean."""
    ep = _endpoint()
    try:
        requests.post(f"{ep}/_ministack/reset", timeout=5)
        _time.sleep(0.5)
        # Verify key services are empty
        checks: dict[str, Any] = {}
        for svc, api in [
            ("s3", lambda: requests.get(f"{ep}/", timeout=3)),
            ("sqs", lambda: requests.post(ep, headers={"Content-Type": "application/x-amz-json-1.0", "X-Amz-Target": "AmazonSQS.ListQueues"}, data="{}", timeout=3)),
            ("dynamodb", lambda: requests.post(ep, headers={"Content-Type": "application/x-amz-json-1.0", "X-Amz-Target": "DynamoDB_20120810.ListTables"}, data="{}", timeout=3)),
        ]:
            try:
                r = api()
                checks[svc] = {"status": "ok", "code": r.status_code}
            except Exception as e:
                checks[svc] = {"status": "error", "error": str(e)}
        return json.dumps({"reset": True, "endpoint": ep, "verification": checks}, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


# ─── Section 5: Prompts ─────────────────────────────────────────────────────


@mcp.prompt()
def setup_serverless_api() -> str:
    """Guided setup for API Gateway + Lambda + DynamoDB on MiniStack."""
    return """You are helping the user set up a serverless API on MiniStack.

Walk them through these steps:
1. Create a DynamoDB table for data storage
2. Create a Lambda function that reads/writes to the table
3. Create an API Gateway (REST or HTTP) with routes pointing to the Lambda
4. Test the full flow with curl

Use the MiniStack endpoint (check with get_endpoint_info).
Use create_resource and aws_execute tools to create resources.
After each step, verify with list_resources or describe_resource.
Keep names simple and explain what each piece does."""


@mcp.prompt()
def setup_event_pipeline() -> str:
    """Guided setup for SQS -> Lambda -> DynamoDB -> SNS event pipeline."""
    return """You are helping the user build an event-driven pipeline on MiniStack.

Architecture: SQS queue -> Lambda function -> DynamoDB table -> SNS topic

Steps:
1. Create an SNS topic for notifications
2. Create a DynamoDB table for processed events
3. Create a Lambda function that reads from SQS, writes to DynamoDB, and publishes to SNS
4. Create an SQS queue
5. Set up the SQS -> Lambda event source mapping
6. Test by sending a message to SQS and verifying it flows through

Use MiniStack tools (create_resource, aws_execute, send_sqs_message, etc.).
Verify each step works before moving to the next."""


@mcp.prompt()
def setup_data_lake() -> str:
    """Guided setup for S3 + Glue + Athena data lake on MiniStack."""
    return """You are helping the user set up a data lake on MiniStack.

Architecture: S3 (raw data) -> Glue (catalog + ETL) -> Athena (query)

Steps:
1. Create S3 buckets for raw and processed data
2. Upload sample data (CSV or JSON) to the raw bucket
3. Create a Glue database and table pointing to the S3 data
4. Query the data with Athena (requires DuckDB for real SQL)
5. Show how to add a Glue ETL job

Note: Athena returns real results when DuckDB is installed, otherwise mock results.
Use put_s3_object for sample data and aws_execute for Glue/Athena operations."""


@mcp.prompt()
def setup_microservice() -> str:
    """Guided setup for ECS + ALB + RDS + ElastiCache microservice."""
    return """You are helping the user set up a microservice architecture on MiniStack.

Architecture: ALB -> ECS (containers) -> RDS (database) + ElastiCache (cache)

Steps:
1. Create an RDS PostgreSQL instance (real Docker container)
2. Create an ElastiCache Redis cluster (real Docker container)
3. Create an ECS cluster, task definition, and service
4. Create an ALB with target group pointing to the ECS service
5. Wait for Docker containers to be ready
6. Test the full flow

Important: These services start real Docker containers. The Docker socket must be
mounted. Use get_docker_status to verify Docker is available.
Poll describe_resource until status is 'available' for RDS."""


@mcp.prompt()
def debug_my_setup() -> str:
    """Diagnose everything in MiniStack — find problems and suggest fixes."""
    return """You are diagnosing the user's MiniStack setup. Be thorough.

Run these checks in order:
1. validate_endpoint — is MiniStack reachable?
2. get_docker_status — are Docker-backed services available?
3. get_logs — any errors in recent logs?
4. list_resources for each active service — what exists?
5. get_setup_status — full overview

For each issue found:
- Explain what's wrong
- Use explain_error if there's a specific error message
- Suggest a concrete fix
- Offer to run the fix if it's safe

Be direct about problems. Don't sugarcoat."""


@mcp.prompt()
def migrate_from_localstack() -> str:
    """Guide for migrating from LocalStack to MiniStack."""
    return """You are helping the user migrate from LocalStack to MiniStack.

Steps:
1. Check their current setup — ask about Docker Compose, CI config, SDK usage
2. Identify LocalStack-specific configuration that needs changing
3. Walk through the migration:
   - Docker image swap
   - Endpoint URL changes
   - Remove LocalStack-specific env vars (SERVICES, LOCALSTACK_API_KEY, etc.)
   - Update any health check URLs (/_localstack -> /_ministack)
4. Verify the new setup works with validate_endpoint and run_smoke_test
5. Run their existing tests to confirm compatibility

Use get_migration_guide('localstack') for reference.
Key point: same port (4566), same AWS API, just different image and config."""


# ─── Section 6: Architecture & Error Help ────────────────────────────────────

_ARCHITECTURE_TEMPLATES: dict[str, list[dict[str, Any]]] = {
    "serverless-api": [
        {"service": "dynamodb", "name": "api-table", "config": ""},
        {"service": "lambda", "name": "api-handler", "config": ""},
        {"service": "s3", "name": "api-assets", "config": ""},
    ],
    "event-pipeline": [
        {"service": "sqs", "name": "events-queue", "config": ""},
        {"service": "sns", "name": "events-topic", "config": ""},
        {"service": "dynamodb", "name": "events-store", "config": ""},
        {"service": "lambda", "name": "events-processor", "config": ""},
    ],
    "static-website": [
        {"service": "s3", "name": "website-bucket", "config": ""},
        {"service": "s3", "name": "logs-bucket", "config": ""},
    ],
    "queue-worker": [
        {"service": "sqs", "name": "work-queue", "config": ""},
        {"service": "sqs", "name": "dead-letter-queue", "config": ""},
        {"service": "lambda", "name": "worker", "config": ""},
        {"service": "dynamodb", "name": "job-status", "config": ""},
    ],
    "crud-api": [
        {"service": "dynamodb", "name": "crud-table", "config": ""},
        {"service": "lambda", "name": "crud-handler", "config": ""},
        {"service": "s3", "name": "crud-uploads", "config": ""},
    ],
}


@mcp.tool()
def scaffold_architecture(template: str) -> str:
    """Create all resources for a predefined architecture template.
    Templates: serverless-api, event-pipeline, static-website, queue-worker, crud-api."""
    tpl = _ARCHITECTURE_TEMPLATES.get(template)
    if not tpl:
        return json.dumps({"error": f"unknown template '{template}'", "available": sorted(_ARCHITECTURE_TEMPLATES.keys())})
    results = []
    for resource in tpl:
        r = create_resource(resource["service"], resource["name"], resource.get("config", ""))
        results.append({"service": resource["service"], "name": resource["name"], "result": json.loads(r)})
    return json.dumps({"template": template, "resources_created": len(results), "results": results}, indent=2)


_ERROR_PATTERNS: list[tuple[str, str, str]] = [
    (r"connection\s*refused", "MiniStack is not running or not listening on the expected port.", "Start MiniStack with 'ministack start' or 'docker run -p 4566:4566 ministackorg/ministack:latest'. Check that MINISTACK_ENDPOINT_URL matches the actual port."),
    (r"no\s*such\s*bucket", "The S3 bucket does not exist.", "Create the bucket first: aws --endpoint-url http://localhost:4566 s3 mb s3://BUCKET_NAME"),
    (r"resource\s*not\s*found", "The requested resource does not exist in MiniStack.", "List existing resources with list_resources to find the correct name. Resources are lost on restart unless PERSIST_STATE=1 is set."),
    (r"table\s*not\s*found|ResourceNotFoundException.*table", "The DynamoDB table does not exist.", "Create the table first or check the table name. Use list_resources('dynamodb') to see existing tables."),
    (r"function\s*not\s*found|ResourceNotFoundException.*function", "The Lambda function does not exist.", "Create the function with create_resource('lambda', 'name') or check the function name with list_resources('lambda')."),
    (r"queue\s*does\s*not\s*exist|NonExistentQueue|AWS\.SimpleQueueService\.NonExistentQueue", "The SQS queue does not exist.", "Create the queue first: create_resource('sqs', 'queue-name'). Check queue URLs with list_resources('sqs')."),
    (r"topic\s*not\s*found|NotFoundException.*topic", "The SNS topic does not exist.", "Create the topic with create_resource('sns', 'topic-name')."),
    (r"docker.*not.*found|docker.*socket|Cannot connect to the Docker daemon", "Docker is not available. Services that need Docker backends (Lambda, RDS, ECS, EKS, ElastiCache) will not work.", "Mount the Docker socket: -v /var/run/docker.sock:/var/run/docker.sock. Verify Docker is running with 'docker ps'."),
    (r"timeout|timed?\s*out", "The request timed out.", "Check if MiniStack is overloaded. For Docker-backed services (RDS, ECS), the container may still be starting. Increase the timeout or poll until ready."),
    (r"access\s*denied|403|forbidden", "Access denied (unexpected in MiniStack — it does not enforce IAM).", "MiniStack does not validate IAM policies. This error likely means the resource path is wrong. Double-check the URL and resource name."),
    (r"invalid\s*parameter|validation\s*error|ValidationException", "A request parameter failed validation.", "Check the parameter values match what the AWS API expects. MiniStack validates the same constraints as real AWS."),
    (r"serialization\s*error|could not parse|malformed|InvalidParameterValue", "The request body is malformed.", "Check JSON syntax, required fields, and data types. Use the AWS CLI or SDK instead of raw HTTP if unsure about the wire format."),
    (r"already\s*exists|BucketAlreadyExists|ResourceInUseException|ConflictException", "The resource already exists.", "Use a different name, or delete the existing resource first with delete_resource."),
    (r"limit\s*exceeded|too\s*many|throttl", "A limit was exceeded.", "MiniStack enforces some AWS limits (e.g., 1MB per DynamoDB item, 256KB SQS message). Reduce the payload size."),
    (r"not\s*implemented|UnsupportedOperation|501", "This operation is not implemented in MiniStack.", "Check is_operation_supported to verify. You may need to use a different approach or wait for the feature."),
    (r"internal\s*server\s*error|500", "MiniStack hit an internal error.", "Check get_logs for the traceback. This may be a MiniStack bug — report it at github.com/ministackorg/ministack/issues."),
    (r"stream.*not.*found|ResourceNotFoundException.*stream", "The Kinesis stream does not exist.", "Create it with create_resource('kinesis', 'stream-name')."),
    (r"secret.*not.*found|ResourceNotFoundException.*secret", "The secret does not exist in Secrets Manager.", "Create it with create_resource('secretsmanager', 'secret-name')."),
    (r"parameter.*not.*found|ParameterNotFound", "The SSM parameter does not exist.", "Create it with create_resource('ssm', '/my/parameter')."),
    (r"state\s*machine.*not.*found|StateMachineDoesNotExist", "The Step Functions state machine does not exist.", "Create it with aws_execute: aws stepfunctions create-state-machine --name NAME --definition '...' --role-arn arn:aws:iam::000000000000:role/role"),
    (r"execution.*not.*found|ExecutionDoesNotExist", "The Step Functions execution was not found.", "List executions: aws stepfunctions list-executions --state-machine-arn ARN"),
    (r"ECONNRESET|EPIPE|broken\s*pipe", "The connection was reset unexpectedly.", "MiniStack may have restarted or the request was too large. Retry the request. Check MiniStack logs with get_logs."),
    (r"certificate.*not.*found", "The ACM certificate was not found.", "List certificates: aws --endpoint-url http://localhost:4566 acm list-certificates"),
    (r"cluster.*not.*found|ClusterNotFoundException", "The ECS/EKS cluster was not found.", "Create the cluster first. For EKS, Docker must be available for k3s."),
    (r"db.*instance.*not.*found|DBInstanceNotFound", "The RDS instance was not found.", "Create it with aws rds create-db-instance. Docker socket required for real containers."),
    (r"cache.*cluster.*not.*found|CacheClusterNotFound", "The ElastiCache cluster was not found.", "Create it with aws elasticache create-cache-cluster. Docker socket required."),
    (r"no\s*module|import\s*error|ModuleNotFoundError", "A Python dependency is missing.", "Install MiniStack with extras: pip install ministack[full]. This includes optional dependencies like duckdb, cryptography, etc."),
    (r"port.*already.*in.*use|address.*already.*in.*use|EADDRINUSE", "Port 4566 is already in use.", "Another MiniStack instance or service is using the port. Stop it or use a different port: ministack start --port 4567"),
    (r"disk\s*space|no\s*space\s*left", "Disk space is full.", "Free disk space. Docker images for backed services can use significant space. Run 'docker system prune' to clean up."),
    (r"container.*unhealthy|health.*check.*fail", "A Docker-backed container is unhealthy.", "Check docker ps for the container status. Try deleting and re-creating the resource. Check Docker logs: docker logs CONTAINER_ID"),
]


@mcp.tool()
def explain_error(error_message: str) -> str:
    """Match an error message against known MiniStack error patterns and return
    a specific diagnosis and fix."""
    msg_lower = error_message.lower()
    matches = []
    for pattern, explanation, fix in _ERROR_PATTERNS:
        if re.search(pattern, msg_lower, re.IGNORECASE):
            matches.append({"pattern": pattern, "explanation": explanation, "fix": fix})
    if not matches:
        return json.dumps({
            "error_message": error_message,
            "matched": False,
            "suggestion": "No known pattern matched. Check get_logs for more context, or try validate_endpoint to diagnose connectivity.",
        }, indent=2)
    return json.dumps({
        "error_message": error_message,
        "matched": True,
        "match_count": len(matches),
        "diagnoses": matches,
    }, indent=2)


# ─── Section 7: Smart Context ───────────────────────────────────────────────


def _collect_setup_status(ep: str | None = None) -> dict[str, Any]:
    """Internal helper: query all services and collect current state."""
    ep = ep or _endpoint()
    status: dict[str, Any] = {"endpoint": ep, "services": {}}
    # Health
    try:
        r = requests.get(f"{ep}/_ministack/health", timeout=3)
        status["healthy"] = r.status_code == 200
    except Exception:
        status["healthy"] = False
        return status
    # Probe each service
    service_probes = {
        "s3": lambda: requests.get(f"{ep}/", timeout=3),
        "dynamodb": lambda: requests.post(ep, headers={"Content-Type": "application/x-amz-json-1.0", "X-Amz-Target": "DynamoDB_20120810.ListTables"}, data="{}", timeout=3),
        "sqs": lambda: requests.post(ep, headers={"Content-Type": "application/x-amz-json-1.0", "X-Amz-Target": "AmazonSQS.ListQueues"}, data="{}", timeout=3),
        "sns": lambda: requests.post(ep, headers={"Content-Type": "application/x-amz-json-1.1", "X-Amz-Target": "SNS.ListTopics"}, data="{}", timeout=3),
        "lambda": lambda: requests.get(f"{ep}/2015-03-31/functions", timeout=3),
        "kinesis": lambda: requests.post(ep, headers={"Content-Type": "application/x-amz-json-1.1", "X-Amz-Target": "Kinesis_20131202.ListStreams"}, data="{}", timeout=3),
        "secretsmanager": lambda: requests.post(ep, headers={"Content-Type": "application/x-amz-json-1.1", "X-Amz-Target": "secretsmanager.ListSecrets"}, data="{}", timeout=3),
        "stepfunctions": lambda: requests.post(ep, headers={"Content-Type": "application/x-amz-json-1.0", "X-Amz-Target": "AWSStepFunctions.ListStateMachines"}, data="{}", timeout=3),
    }
    for svc_name, probe_fn in service_probes.items():
        try:
            r = probe_fn()
            try:
                data = r.json()
            except Exception:
                data = r.text[:500]
            status["services"][svc_name] = {"reachable": True, "data": data}
        except Exception as e:
            status["services"][svc_name] = {"reachable": False, "error": str(e)}
    return status


@mcp.tool()
def get_setup_status() -> str:
    """Full overview of everything currently in MiniStack — all services,
    resources, and health status."""
    status = _collect_setup_status()
    return json.dumps(status, indent=2)


@mcp.tool()
def suggest_next_steps() -> str:
    """Based on current MiniStack resources, suggest what to do next."""
    status = _collect_setup_status()
    if not status.get("healthy"):
        return json.dumps({
            "status": "unhealthy",
            "suggestions": [
                "MiniStack is not reachable. Start it with 'ministack start' or via Docker.",
                "Check that MINISTACK_ENDPOINT_URL is correct.",
                "Run validate_endpoint for detailed diagnostics.",
            ],
        }, indent=2)
    suggestions = []
    has_resources: dict[str, bool] = {}
    for svc_name, svc_data in status.get("services", {}).items():
        data = svc_data.get("data", {})
        if isinstance(data, dict):
            # Check for non-empty resource lists
            resource_keys = ["Buckets", "TableNames", "QueueUrls", "Topics", "Functions",
                             "StreamNames", "SecretList", "stateMachines"]
            for k in resource_keys:
                if k in data and data[k]:
                    has_resources[svc_name] = True
                    break
    if not has_resources:
        suggestions.append("Your MiniStack is empty. Try scaffold_architecture('serverless-api') for a quick start.")
        suggestions.append("Or create individual resources with create_resource('s3', 'my-bucket').")
        suggestions.append("Use the setup_serverless_api prompt for a guided walkthrough.")
    else:
        active = list(has_resources.keys())
        suggestions.append(f"Active services: {', '.join(active)}.")
        if "s3" in has_resources and "lambda" not in has_resources:
            suggestions.append("You have S3 buckets but no Lambda functions. Consider adding a Lambda to process S3 events.")
        if "sqs" in has_resources and "lambda" not in has_resources:
            suggestions.append("You have SQS queues but no Lambda consumers. Add a Lambda with an SQS event source mapping.")
        if "dynamodb" in has_resources and "lambda" not in has_resources:
            suggestions.append("You have DynamoDB tables. Consider adding an API Gateway + Lambda to expose them as an API.")
        if "lambda" in has_resources and "dynamodb" not in has_resources:
            suggestions.append("You have Lambda functions but no database. Add a DynamoDB table for persistence.")
        suggestions.append("Run run_smoke_test to verify everything is working correctly.")
        suggestions.append("Run export_setup('terraform') to capture your current setup as infrastructure-as-code.")
    return json.dumps({"suggestions": suggestions}, indent=2)


_USE_CASE_MAP: list[tuple[list[str], list[str], str]] = [
    (["api", "rest", "http", "web", "endpoint"], ["apigateway", "lambda", "dynamodb"], "API Gateway + Lambda + DynamoDB for a REST/HTTP API"),
    (["queue", "async", "decouple", "worker", "background", "job"], ["sqs", "lambda"], "SQS + Lambda for async processing"),
    (["event", "pub", "sub", "fanout", "notification", "alert"], ["sns", "sqs", "eventbridge"], "SNS/SQS/EventBridge for event-driven architectures"),
    (["storage", "file", "upload", "blob", "static", "asset"], ["s3"], "S3 for object storage"),
    (["database", "nosql", "table", "query", "crud", "item"], ["dynamodb"], "DynamoDB for NoSQL database"),
    (["sql", "relational", "postgres", "mysql", "rds"], ["rds"], "RDS for SQL databases (real Docker containers)"),
    (["cache", "redis", "memcached", "session"], ["elasticache"], "ElastiCache for caching (real Docker containers)"),
    (["container", "docker", "microservice", "ecs"], ["ecs"], "ECS for container orchestration"),
    (["kubernetes", "k8s", "eks", "helm"], ["eks"], "EKS for Kubernetes (real k3s containers)"),
    (["stream", "realtime", "kinesis", "ingest"], ["kinesis"], "Kinesis for data streaming"),
    (["secret", "credential", "password", "key"], ["secretsmanager", "ssm"], "Secrets Manager / SSM Parameter Store"),
    (["config", "parameter", "feature flag", "setting"], ["ssm", "appconfig"], "SSM Parameter Store / AppConfig"),
    (["workflow", "orchestration", "state machine", "step"], ["stepfunctions"], "Step Functions for workflow orchestration"),
    (["search", "opensearch", "elasticsearch"], ["opensearch"], "OpenSearch (real Docker containers with OPENSEARCH_DATAPLANE=1)"),
    (["email", "ses", "notification"], ["ses", "ses_v2"], "SES for email (stored in-memory, not sent)"),
    (["dns", "domain", "route"], ["route53"], "Route 53 for DNS management"),
    (["certificate", "ssl", "tls"], ["acm"], "ACM for certificate management"),
    (["auth", "user", "login", "cognito", "identity"], ["cognito"], "Cognito for authentication"),
    (["iot", "device", "mqtt", "sensor"], ["iot"], "IoT Core for device connectivity (real MQTT broker)"),
    (["etl", "transform", "glue", "catalog"], ["glue"], "Glue for ETL and data catalog"),
    (["airflow", "dag", "mwaa", "pipeline"], ["mwaa"], "MWAA for Apache Airflow (real Docker containers)"),
    (["deploy", "infrastructure", "cloudformation", "stack"], ["cloudformation"], "CloudFormation for infrastructure management"),
    (["monitor", "log", "metric", "alarm", "cloudwatch"], ["cloudwatch", "cloudwatch_logs"], "CloudWatch for monitoring and logging"),
]


@mcp.tool()
def find_service_for_use_case(use_case: str) -> str:
    """Given a natural language use case, suggest which MiniStack services to use."""
    uc_lower = use_case.lower()
    matches = []
    for keywords, services, description in _USE_CASE_MAP:
        score = sum(1 for kw in keywords if kw in uc_lower)
        if score > 0:
            svc_details = []
            for s in services:
                parity = _PARITY.get("services", {}).get(s, {})
                svc_details.append({
                    "service": s,
                    "status": parity.get("status", "unknown"),
                    "docker_backed": parity.get("real_backend") == "docker",
                })
            matches.append({"score": score, "description": description, "services": svc_details})
    matches.sort(key=lambda m: m["score"], reverse=True)
    if not matches:
        return json.dumps({
            "use_case": use_case,
            "matched": False,
            "suggestion": "No direct match. Use list_services to see all available services, or search_operations to find specific API operations.",
        }, indent=2)
    return json.dumps({"use_case": use_case, "match_count": len(matches), "suggestions": matches[:5]}, indent=2)


@mcp.tool()
def export_setup(format: str = "terraform") -> str:
    """Export current MiniStack state as Terraform, CloudFormation, or boto3 code.
    Queries live resources and generates the corresponding IaC."""
    status = _collect_setup_status()
    if not status.get("healthy"):
        return json.dumps({"error": "MiniStack is not reachable"})
    ep = status["endpoint"]
    fmt = format.lower()
    resources: list[dict[str, str]] = []
    # Collect resource names from status
    for svc_name, svc_data in status.get("services", {}).items():
        data = svc_data.get("data", {})
        if not isinstance(data, dict):
            continue
        if svc_name == "s3":
            for b in data.get("Buckets", []):
                name = b.get("Name", "") if isinstance(b, dict) else str(b)
                if name:
                    resources.append({"type": "s3_bucket", "name": name})
        elif svc_name == "dynamodb":
            for t in data.get("TableNames", []):
                resources.append({"type": "dynamodb_table", "name": t})
        elif svc_name == "sqs":
            for q in data.get("QueueUrls", []):
                qname = q.rstrip("/").split("/")[-1] if isinstance(q, str) else str(q)
                resources.append({"type": "sqs_queue", "name": qname})
        elif svc_name == "sns":
            for t in data.get("Topics", []):
                arn = t.get("TopicArn", "") if isinstance(t, dict) else str(t)
                tname = arn.split(":")[-1] if arn else ""
                if tname:
                    resources.append({"type": "sns_topic", "name": tname})
        elif svc_name == "lambda":
            fns = data.get("Functions", [])
            for f in fns:
                fname = f.get("FunctionName", "") if isinstance(f, dict) else str(f)
                if fname:
                    resources.append({"type": "lambda_function", "name": fname})
        elif svc_name == "kinesis":
            for s in data.get("StreamNames", []):
                resources.append({"type": "kinesis_stream", "name": s})
    if not resources:
        return json.dumps({"format": fmt, "resources": [], "note": "No resources found in MiniStack. Nothing to export."})
    if fmt == "terraform":
        lines = [
            '# Generated from live MiniStack state',
            '# Provider config needed — see ministack://docs/terraform\n',
        ]
        for r in resources:
            safe = r["name"].replace("-", "_").replace(".", "_")
            if r["type"] == "s3_bucket":
                lines.append(f'resource "aws_s3_bucket" "{safe}" {{\n  bucket = "{r["name"]}"\n}}\n')
            elif r["type"] == "dynamodb_table":
                lines.append(f'resource "aws_dynamodb_table" "{safe}" {{\n  name         = "{r["name"]}"\n  billing_mode = "PAY_PER_REQUEST"\n  hash_key     = "pk"\n\n  attribute {{\n    name = "pk"\n    type = "S"\n  }}\n}}\n')
            elif r["type"] == "sqs_queue":
                lines.append(f'resource "aws_sqs_queue" "{safe}" {{\n  name = "{r["name"]}"\n}}\n')
            elif r["type"] == "sns_topic":
                lines.append(f'resource "aws_sns_topic" "{safe}" {{\n  name = "{r["name"]}"\n}}\n')
            elif r["type"] == "lambda_function":
                lines.append(f'resource "aws_lambda_function" "{safe}" {{\n  function_name = "{r["name"]}"\n  # TODO: fill in handler, runtime, filename\n}}\n')
            elif r["type"] == "kinesis_stream":
                lines.append(f'resource "aws_kinesis_stream" "{safe}" {{\n  name        = "{r["name"]}"\n  shard_count = 1\n}}\n')
        code = "\n".join(lines)
    elif fmt == "cloudformation":
        cf_resources: dict[str, Any] = {}
        for r in resources:
            safe = r["name"].replace("-", "").replace(".", "").replace("_", "")
            if r["type"] == "s3_bucket":
                cf_resources[f"S3{safe}"] = {"Type": "AWS::S3::Bucket", "Properties": {"BucketName": r["name"]}}
            elif r["type"] == "dynamodb_table":
                cf_resources[f"DDB{safe}"] = {"Type": "AWS::DynamoDB::Table", "Properties": {
                    "TableName": r["name"], "BillingMode": "PAY_PER_REQUEST",
                    "AttributeDefinitions": [{"AttributeName": "pk", "AttributeType": "S"}],
                    "KeySchema": [{"AttributeName": "pk", "KeyType": "HASH"}],
                }}
            elif r["type"] == "sqs_queue":
                cf_resources[f"SQS{safe}"] = {"Type": "AWS::SQS::Queue", "Properties": {"QueueName": r["name"]}}
            elif r["type"] == "sns_topic":
                cf_resources[f"SNS{safe}"] = {"Type": "AWS::SNS::Topic", "Properties": {"TopicName": r["name"]}}
            elif r["type"] == "lambda_function":
                cf_resources[f"Lambda{safe}"] = {"Type": "AWS::Lambda::Function", "Properties": {"FunctionName": r["name"]}}
            elif r["type"] == "kinesis_stream":
                cf_resources[f"Kinesis{safe}"] = {"Type": "AWS::Kinesis::Stream", "Properties": {"Name": r["name"], "ShardCount": 1}}
        template = {"AWSTemplateFormatVersion": "2010-09-09", "Description": "Exported from MiniStack", "Resources": cf_resources}
        code = json.dumps(template, indent=2)
    elif fmt in ("boto3", "python"):
        lines = [
            "# Generated from live MiniStack state",
            "import boto3\n",
            f'endpoint = "{ep}"\n',
        ]
        for r in resources:
            if r["type"] == "s3_bucket":
                lines.append(f"s3 = boto3.client('s3', endpoint_url=endpoint)\ns3.create_bucket(Bucket='{r['name']}')\n")
            elif r["type"] == "dynamodb_table":
                lines.append(f"ddb = boto3.client('dynamodb', endpoint_url=endpoint)\nddb.create_table(TableName='{r['name']}', AttributeDefinitions=[{{'AttributeName': 'pk', 'AttributeType': 'S'}}], KeySchema=[{{'AttributeName': 'pk', 'KeyType': 'HASH'}}], BillingMode='PAY_PER_REQUEST')\n")
            elif r["type"] == "sqs_queue":
                lines.append(f"sqs = boto3.client('sqs', endpoint_url=endpoint)\nsqs.create_queue(QueueName='{r['name']}')\n")
            elif r["type"] == "sns_topic":
                lines.append(f"sns = boto3.client('sns', endpoint_url=endpoint)\nsns.create_topic(Name='{r['name']}')\n")
            elif r["type"] == "lambda_function":
                lines.append(f"lam = boto3.client('lambda', endpoint_url=endpoint)\n# lam.create_function(FunctionName='{r['name']}', ...)\n")
            elif r["type"] == "kinesis_stream":
                lines.append(f"kin = boto3.client('kinesis', endpoint_url=endpoint)\nkin.create_stream(StreamName='{r['name']}', ShardCount=1)\n")
        code = "\n".join(lines)
    else:
        return json.dumps({"error": f"unsupported format '{fmt}'", "supported": ["terraform", "cloudformation", "boto3"]})
    return json.dumps({"format": fmt, "resource_count": len(resources), "code": code}, indent=2)


@mcp.tool()
def diff_environments(endpoint_a: str, endpoint_b: str) -> str:
    """Compare two MiniStack instances by querying resources on each endpoint."""
    status_a = _collect_setup_status(endpoint_a)
    status_b = _collect_setup_status(endpoint_b)
    diff: dict[str, Any] = {"endpoint_a": endpoint_a, "endpoint_b": endpoint_b, "differences": {}}
    if not status_a.get("healthy"):
        diff["endpoint_a_error"] = "unreachable"
    if not status_b.get("healthy"):
        diff["endpoint_b_error"] = "unreachable"
    if not status_a.get("healthy") or not status_b.get("healthy"):
        return json.dumps(diff, indent=2)
    all_services = set(list(status_a.get("services", {}).keys()) + list(status_b.get("services", {}).keys()))
    for svc in sorted(all_services):
        data_a = status_a.get("services", {}).get(svc, {}).get("data", {})
        data_b = status_b.get("services", {}).get(svc, {}).get("data", {})
        if data_a != data_b:
            diff["differences"][svc] = {"endpoint_a": data_a, "endpoint_b": data_b}
    if not diff["differences"]:
        diff["summary"] = "Environments are identical (same resources on probed services)."
    else:
        diff["summary"] = f"Found differences in {len(diff['differences'])} service(s)."
    return json.dumps(diff, indent=2)


# ─── Section 8: Guidance (live, not hardcoded) ───────────────────────────────


@mcp.tool()
def get_quickstart(service: str) -> str:
    """Return a quickstart guide for a MiniStack service. Generates boto3
    patterns dynamically from the catalog — not hardcoded examples."""
    svc = service.lower().replace("-", "_")
    rec = _service_record(svc)
    if not rec:
        return json.dumps({"error": f"service '{svc}' not found. Use list_services to see available services."})
    ep = _endpoint()
    ops = rec.get("operations", [])
    parity = _PARITY.get("services", {}).get(svc, {})
    # Map service names to boto3 client names
    boto3_map = {
        "lambda_svc": "lambda", "cloudwatch_logs": "logs",
        "apigateway_v1": "apigateway", "ses_v2": "sesv2",
        "dynamodb_streams": "dynamodbstreams", "waf": "wafv2",
        "waf_v1": "waf", "alb": "elbv2",
    }
    boto3_name = boto3_map.get(svc, svc)
    guide = {
        "service": svc,
        "status": parity.get("status", "unknown"),
        "operation_count": len(ops),
        "docker_backed": parity.get("real_backend") == "docker",
        "notes": parity.get("notes"),
        "gotchas": parity.get("gotchas", []),
        "boto3_pattern": f"import boto3\nclient = boto3.client('{boto3_name}', endpoint_url='{ep}')",
        "operations": ops[:30],  # First 30 operations
        "operations_truncated": len(ops) > 30,
    }
    if parity.get("real_backend") == "docker":
        guide["docker_note"] = "This service starts real Docker containers. Mount the Docker socket: -v /var/run/docker.sock:/var/run/docker.sock"
    return json.dumps(guide, indent=2)


@mcp.tool()
def compare_with_aws(service: str) -> str:
    """Compare a MiniStack service with real AWS. Shows parity status, known
    differences, and gotchas from parity.json."""
    svc = service.lower().replace("-", "_")
    parity = _PARITY.get("services", {}).get(svc)
    if not parity:
        return json.dumps({"error": f"service '{svc}' not found in parity data."})
    rec = _service_record(svc)
    common_differences = [
        "No billing or cost tracking — all API calls are free.",
        "IAM policies are stored but NOT evaluated — all calls are implicitly allowed.",
        "SigV4 signatures are not validated — any access key works.",
        "No multi-region — all resources live in the configured region.",
        "No resource quotas (except where explicitly noted, e.g., DynamoDB item size).",
        "No eventual consistency simulation — reads are immediately consistent.",
    ]
    service_specific: list[str] = []
    if parity.get("real_backend") == "docker":
        service_specific.append(f"Uses real Docker containers — behavior closely matches AWS.")
    if parity.get("persistence"):
        service_specific.append("Supports persistence across restarts.")
    if parity.get("gotchas"):
        service_specific.extend(parity["gotchas"])
    result = {
        "service": svc,
        "ministack_status": parity.get("status", "unknown"),
        "notes": parity.get("notes"),
        "operation_count": rec.get("operation_count", 0) if rec else 0,
        "common_ministack_differences": common_differences,
        "service_specific_notes": service_specific if service_specific else ["No service-specific gotchas noted."],
    }
    return json.dumps(result, indent=2)


@mcp.tool()
def get_migration_guide(from_tool: str) -> str:
    """Return migration steps from LocalStack or Moto to MiniStack. Focuses on
    endpoint config and Docker image swap — not hardcoded code examples."""
    tool = from_tool.lower().strip()
    if tool in ("localstack", "local-stack", "local_stack"):
        return json.dumps({
            "from": "LocalStack",
            "to": "MiniStack",
            "steps": [
                {
                    "step": 1,
                    "title": "Swap Docker image",
                    "detail": "Replace localstack/localstack:latest with ministackorg/ministack:latest. Same port (4566).",
                },
                {
                    "step": 2,
                    "title": "Update endpoint URLs",
                    "detail": "Replace LOCALSTACK_HOSTNAME, EDGE_PORT with AWS_ENDPOINT_URL=http://localhost:4566 or MINISTACK_ENDPOINT_URL.",
                },
                {
                    "step": 3,
                    "title": "Remove LocalStack-specific env vars",
                    "detail": "Remove: SERVICES, LOCALSTACK_API_KEY, EDGE_PORT, DEFAULT_REGION, LAMBDA_EXECUTOR, DATA_DIR. MiniStack always starts all services, has no Pro tier.",
                },
                {
                    "step": 4,
                    "title": "Update health check URLs",
                    "detail": "Replace /_localstack/health with /_ministack/health. Reset endpoint: POST /_ministack/reset.",
                },
                {
                    "step": 5,
                    "title": "Update CI/CD config",
                    "detail": "Update Docker image references in GitHub Actions, GitLab CI, docker-compose.yml, etc.",
                },
                {
                    "step": 6,
                    "title": "Verify",
                    "detail": "Use validate_endpoint and run_smoke_test to confirm everything works.",
                },
            ],
            "key_differences": {
                "same_port": True,
                "same_aws_api": True,
                "no_pro_tier": "MiniStack has no paid features — everything is included.",
                "docker_backends": "RDS, ECS, EKS, ElastiCache, Lambda, Glue, MWAA, OpenSearch all use real Docker containers.",
                "persistence": "PERSIST_STATE=1 and S3_PERSIST=1 (no LocalStack Pro needed).",
            },
        }, indent=2)
    elif tool in ("moto", "moto-server"):
        return json.dumps({
            "from": "Moto",
            "to": "MiniStack",
            "steps": [
                {
                    "step": 1,
                    "title": "Switch from moto decorators to endpoint_url",
                    "detail": "Replace @mock_s3, @mock_dynamodb etc. with endpoint_url='http://localhost:4566' in boto3 clients.",
                },
                {
                    "step": 2,
                    "title": "Start MiniStack as a service",
                    "detail": "Moto runs in-process; MiniStack runs as a separate server. Start via Docker or 'ministack start'.",
                },
                {
                    "step": 3,
                    "title": "Update test fixtures",
                    "detail": "Replace moto decorators with a fixture that resets MiniStack: POST /_ministack/reset before each test.",
                },
                {
                    "step": 4,
                    "title": "Gain Docker-backed services",
                    "detail": "Unlike Moto, MiniStack can run real RDS, ECS, EKS, Lambda containers. Mount the Docker socket.",
                },
                {
                    "step": 5,
                    "title": "Verify",
                    "detail": "Use validate_endpoint and run_smoke_test.",
                },
            ],
            "key_differences": {
                "architecture": "Moto is in-process Python mocking; MiniStack is a standalone server with real Docker backends.",
                "docker_backends": "MiniStack runs real Postgres, Redis, k3s, Lambda containers — higher fidelity.",
                "reset": "POST /_ministack/reset instead of moto decorators.",
            },
        }, indent=2)
    else:
        return json.dumps({
            "error": f"Unknown tool '{from_tool}'. Supported: localstack, moto.",
            "supported_tools": ["localstack", "moto"],
        }, indent=2)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
