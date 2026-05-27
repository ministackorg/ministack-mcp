# MiniStack FAQ

## General

**Q: What port does MiniStack use?**
A: Port 4566 by default. All services share this single port.

**Q: Does MiniStack validate AWS credentials?**
A: No. SigV4 signatures are not validated. The access key ID is read to derive
the account ID, but secret keys are not checked. Use any value.

**Q: Is data persistent?**
A: By default no — all state is in-memory and lost on restart. Enable
`PERSIST_STATE=1` for Docker-backed services and `S3_PERSIST=1` for S3 objects.

**Q: How is MiniStack different from LocalStack?**
A: MiniStack is a lightweight, single-binary emulator focused on correctness
over breadth. No Pro tier. Docker-backed services (RDS, Lambda, ECS, EKS) run
real containers. Single port, single process.

## Services

**Q: Which services run real backends?**
A: Lambda, RDS, ECS, EKS, ElastiCache, OpenSearch, Glue, and MWAA spawn real
Docker containers. Other services are in-memory emulations.

**Q: Does IAM actually enforce policies?**
A: No. IAM resources (users, roles, policies) are stored but policies are not
evaluated on API calls. All calls are implicitly allowed.

**Q: Does Lambda support all runtimes?**
A: Python and Node.js run natively with warm worker pools. Go, Rust, and C++
use `provided.al2023`/`provided.al2` via Docker RIE. Java and .NET are not
currently supported.

**Q: Is there billing/cost tracking?**
A: No. MiniStack does not meter or bill. Cost-related APIs (CUR) are stubs.

## Networking

**Q: Can containers reach MiniStack?**
A: Yes. Docker-backed services run on a `ministack` network. Use
`host.docker.internal:4566` from inside containers.

**Q: Can I use virtual-hosted S3 URLs?**
A: MiniStack uses path-style S3 by default (`http://localhost:4566/bucket/key`).
Set `s3_use_path_style = true` in Terraform or `forcePathStyle: true` in SDKs.

## Troubleshooting

**Q: `ConnectionRefusedError` on port 4566**
A: MiniStack is not running. Start it with `ministack start` or via Docker.

**Q: Lambda invocation returns 500**
A: Check that the Docker socket is mounted. Lambda needs Docker to run function
code. Also verify the handler path matches your code layout.

**Q: RDS instance stuck in "creating"**
A: The Docker container is still starting. Poll `DescribeDBInstances` until
status is `available`. This can take 10-30 seconds.

**Q: "service not found" in MCP tools**
A: Service names are lowercase and may differ from boto3 client names.
Use `list_services` to see all available names.
