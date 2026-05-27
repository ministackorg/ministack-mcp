# MiniStack Quickstart

## Prerequisites

- Python 3.10+ or Docker
- MiniStack running on `http://localhost:4566` (default)

## Start MiniStack

```bash
# pip install
pip install ministack
ministack start

# or Docker
docker run -p 4566:4566 ministackorg/ministack:latest
```

## Verify it works

```bash
curl http://localhost:4566/_ministack/health
```

## Use the AWS CLI

Point any AWS CLI command at MiniStack with `--endpoint-url`:

```bash
# S3
aws --endpoint-url http://localhost:4566 s3 mb s3://my-bucket
aws --endpoint-url http://localhost:4566 s3 cp file.txt s3://my-bucket/

# DynamoDB
aws --endpoint-url http://localhost:4566 dynamodb create-table \
  --table-name my-table \
  --attribute-definitions AttributeName=pk,AttributeType=S \
  --key-schema AttributeName=pk,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST

# SQS
aws --endpoint-url http://localhost:4566 sqs create-queue --queue-name my-queue

# SNS
aws --endpoint-url http://localhost:4566 sns create-topic --name my-topic

# Lambda
aws --endpoint-url http://localhost:4566 lambda create-function \
  --function-name hello \
  --runtime python3.12 \
  --handler index.handler \
  --zip-file fileb://function.zip \
  --role arn:aws:iam::000000000000:role/lambda-role
```

## Environment shortcut

Set `AWS_ENDPOINT_URL` to avoid repeating `--endpoint-url`:

```bash
export AWS_ENDPOINT_URL=http://localhost:4566
aws s3 ls  # now targets MiniStack automatically
```

## SDK configuration

All AWS SDKs accept an `endpoint_url` parameter:

```python
import boto3
client = boto3.client('s3', endpoint_url='http://localhost:4566')
```

```javascript
const { S3Client } = require('@aws-sdk/client-s3');
const client = new S3Client({ endpoint: 'http://localhost:4566', forcePathStyle: true });
```

## Reset state

```bash
curl -X POST http://localhost:4566/_ministack/reset
```
