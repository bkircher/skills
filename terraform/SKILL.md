---
name: terraform
description: Use when writing Terraform.
---

# Modern Terraform (v1.11+) Best Practices

- Use `try()` for fail-safe defaults; prefer over `element(concat())` for robust error handling.
- Set `nullable = false` in variables to prevent null assignments and reduce misconfiguration.
- Use `moved` blocks to refactor resources/modules efficiently, avoiding destroy/recreate cycles.
- Apply `optional()` with defaults for flexible object field handling.
- Use Terraform's native test framework to improve module reliability.
- Run unit tests with mock providers to avoid impacting real infrastructure.
- Apply provider-defined functions for resource configuration as needed.
- Validate relationships between variables for input correctness.
- Use write-only arguments for secrets, when supported, to avoid persisting them in state files.

# Naming Conventions

## Resources

```hcl
# Use descriptive, contextual names:
resource "aws_instance" "web_server" {}
resource "aws_s3_bucket" "application_logs" {}

# Avoid generic names:
resource "aws_instance" "main" {}
resource "aws_s3_bucket" "bucket" {}

# Use "this" only for primary resources inside reusable modules (singletons):
resource "aws_vpc" "this" {}
resource "aws_security_group" "this" {}
```

## Variables

```hcl
# Prefer context-rich, specific names:
var.vpc_cidr_block
var.database_instance_class
```

## File Structure

- `main.tf`: Core resources.
- `variables.tf`: Input variables.
- `outputs.tf`: Output values.
- `versions.tf`: Provider versions.
- `data.tf`: (Optional) Data sources.

# Directory Structure

- Separate environment configs from modules.
- Use `examples/` for usage docs and test fixtures.

```
envs/            # Environment configs
├── prod/
├── staging/
└── dev/
modules/         # Reusable modules
├── networking/
├── compute/
└── data/
examples/        # Usage/test examples
├── complete/
└── minimal/
```

# Module Hierarchy

**Resource → Resource Module → Infrastructure Module → Composition**

| Type                | Use Case                            | Scope                                |
| ------------------- | ----------------------------------- | ------------------------------------ |
| **Resource Module** | Group related resources             | VPC + subnets, SG + rules            |
| **Infra Module**    | Combine resource modules for a goal | Multiple modules, one region/account |
| **Composition**     | Full infrastructure deployment      | Across regions/accounts              |

# Patterns

Follow these for conditionals and stable resource addressing:

**Boolean condition:**

```hcl
# Boolean condition using for_each (stable addressing, no [0] index):
resource "aws_nat_gateway" "this" {
  for_each = var.create_nat_gateway ? { this = true } : {}

  # example fields:
  allocation_id = aws_eip.nat[each.key].id
  subnet_id     = aws_subnet.public[each.key].id
}
```

**Stable referencing with for_each:**

```hcl
# Safer when removing AZs:
resource "aws_subnet" "private" {
  for_each = toset(var.availability_zones)
  availability_zone = each.key
}

# count risks larger changes (don't do this):
resource "aws_subnet" "private" {
  count = length(var.availability_zones)
  availability_zone = var.availability_zones[count.index]
}
```

# Security Guidelines

- Do not hardcode secrets in `.tf` or `.tfvars`; avoid committing secrets to version control.
- Mark secret variables as `sensitive = true` for UI redaction.
- Enable encryption for supported resources.
- Avoid wide-open rules in security groups (e.g., `0.0.0.0/0`).
- Enforce least privilege for security group rules.

## AWS-specific

- Store secrets in AWS Secrets Manager or Parameter Store.
- Avoid deploying resources in the default VPC; create dedicated VPCs.

## Azure-specific

- Use dedicated VNets and segmented subnets; control egress explicitly.
- Avoid public access on Storage Accounts, Key Vault, SQL, etc., unless required.
- Prefer Private Endpoints (Private Link) and service endpoints.
- Store secrets in Azure Key Vault.
