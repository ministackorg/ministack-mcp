# MiniStack with Terraform

## Provider configuration

```hcl
provider "aws" {
  region                      = "us-east-1"
  access_key                  = "test"
  secret_key                  = "test"
  skip_credentials_validation = true
  skip_metadata_api_check     = true
  skip_requesting_account_id  = true

  endpoints {
    # Point every service at MiniStack
    s3             = "http://localhost:4566"
    dynamodb       = "http://localhost:4566"
    lambda         = "http://localhost:4566"
    sqs            = "http://localhost:4566"
    sns            = "http://localhost:4566"
    iam            = "http://localhost:4566"
    sts            = "http://localhost:4566"
    cloudformation = "http://localhost:4566"
    cloudwatch     = "http://localhost:4566"
    kinesis        = "http://localhost:4566"
    secretsmanager = "http://localhost:4566"
    ssm            = "http://localhost:4566"
    stepfunctions  = "http://localhost:4566"
    apigateway     = "http://localhost:4566"
    apigatewayv2   = "http://localhost:4566"
    ec2            = "http://localhost:4566"
    ecs            = "http://localhost:4566"
    eks            = "http://localhost:4566"
    rds            = "http://localhost:4566"
    route53        = "http://localhost:4566"
    acm            = "http://localhost:4566"
    kms            = "http://localhost:4566"
    wafv2          = "http://localhost:4566"
  }

  s3_use_path_style = true
}
```

## S3 backend (optional)

Store Terraform state in MiniStack S3:

```hcl
terraform {
  backend "s3" {
    bucket                      = "tf-state"
    key                         = "ministack/terraform.tfstate"
    region                      = "us-east-1"
    endpoint                    = "http://localhost:4566"
    access_key                  = "test"
    secret_key                  = "test"
    skip_credentials_validation = true
    skip_metadata_api_check     = true
    force_path_style            = true
  }
}
```

Create the bucket first:

```bash
aws --endpoint-url http://localhost:4566 s3 mb s3://tf-state
```

## CloudFormation resources

MiniStack supports 77 CloudFormation resource types. Terraform's AWS provider
talks the native API, not CloudFormation, so most resources work directly.

## Tips

- Use `s3_use_path_style = true` — MiniStack uses path-style S3 URLs.
- `skip_credentials_validation` and `skip_metadata_api_check` prevent Terraform
  from making calls MiniStack does not need.
- Run `terraform plan` freely — read operations are idempotent in MiniStack.
- After `ministack reset`, run `terraform apply` to re-create resources.
