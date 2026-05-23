# infragen — Project Context Document
> Full project plan for Claude Code. Read this entirely before writing any code.

---

## What This Project Is

`infragen` is a CLI tool that deploys web applications to AWS by scanning the codebase, generating Terraform, auditing security, estimating cost, and deploying — all from a single command run inside any supported project directory.

The user runs one command. The tool figures out what the project is, what infrastructure it needs, generates everything, shows a full review in the terminal, and deploys after explicit approval.

---

## Core Design Principles

1. **The terminal is the only interface.** No web UI, no browser, no external dashboard. Everything — scan results, security findings, cost tables, secrets input, deployment logs — happens in the CLI.
2. **Never read `.env`.** Only `.env.example` is read. Real secrets are entered interactively in the terminal and sent directly to AWS SSM. They are never written to disk.
3. **Static analysis first, LLM second.** The codebase scanner uses regex, file parsing, and AST analysis for 80% of detection. The LLM (Groq) is called only for ambiguous cases that static analysis cannot resolve confidently.
4. **Explicit over implicit.** Every assumption made is shown to the user. Every inferred resource is flagged. Nothing is deployed without explicit `y` approval.
5. **Free tier by default.** Default deployment uses AWS free tier eligible resources. Production-grade architecture requires an explicit `--prod` flag.
6. **One service per deployment.** Each `infragen deploy` session deploys exactly one service — either a backend API or a frontend. The tool does not handle multi-service deployments. If a project has both frontend and backend, the user runs `infragen deploy` twice from two different directories.

---

## Supported Runtimes and Frameworks

This is the complete support matrix. Nothing outside this matrix is supported. If an unsupported framework is detected, the tool exits with a clear error message listing what is supported.

```
Runtime    Framework    Service Type         Infrastructure (free)      Infrastructure (--prod)
────────────────────────────────────────────────────────────────────────────────────────────────
Python     FastAPI      Backend API          EC2 t3.micro + RDS         ECS Fargate + RDS + ALB
Python     Flask        Backend API          EC2 t3.micro + RDS         ECS Fargate + RDS + ALB
Python     Django       Backend API          EC2 t3.micro + RDS         ECS Fargate + RDS + ALB
Node.js    Express      Backend API          EC2 t3.micro + RDS         ECS Fargate + RDS + ALB
Node.js    Next.js SSR  Frontend SSR         EC2 t3.micro               ECS Fargate + ALB
Node.js    Next.js      Frontend Static      S3 + CloudFront            S3 + CloudFront (same)
           (output:export)
Node.js    React        Frontend Static      S3 + CloudFront            S3 + CloudFront (same)
```

**Notes:**
- Next.js is SSR by default. If `next.config.js` contains `output: 'export'`, it is treated as static.
- React covers both Create React App (output: `build/`) and Vite (output: `dist/`).
- Static frontend infrastructure is identical in free and prod modes. S3 + CloudFront is already free tier compatible and production ready.
- Django requires `gunicorn` in `requirements.txt`. If missing, the tool adds it automatically and warns the user.
- Flask requires `gunicorn` in `requirements.txt`. Same behaviour as Django.

---

## Prerequisites

These must exist on the user's machine before `infragen deploy` works. The `infragen doctor` command checks all of them.

### Always Required
- **AWS CLI** — installed and configured via `aws configure`
- **AWS account** — with appropriate IAM permissions (see below)
- **Terraform** — installed and available in PATH
- **Python 3.11+** — to run infragen itself
- **`.env.example`** — in the project root, listing all env var names with empty values

### Required for Backend and SSR Frontend (not needed for React static)
- **Docker** — installed and running daemon

### Required for Static Frontend without Dockerfile (not needed if Dockerfile exists)
- **Node.js** — to run `npm run build` locally

### Not Required
- Any specific cloud SDK beyond what infragen installs as a dependency
- kubectl, Helm, or any Kubernetes tooling
- Any specific Python version manager

---

## AWS IAM Permissions Required

The user's IAM user or role needs these managed policies:

```
AmazonVPCFullAccess
AmazonECS_FullAccess
AmazonRDSFullAccess
AmazonS3FullAccess
CloudFrontFullAccess
AmazonSSMFullAccess
ElasticLoadBalancingFullAccess
AmazonEC2ContainerRegistryFullAccess
AmazonEC2FullAccess
IAMFullAccess
AWSCertificateManagerFullAccess
```

For simplicity during development and learning, `AdministratorAccess` is acceptable but should not be used on production AWS accounts.

The `infragen doctor` command validates each permission using IAM policy simulation (no resources created) before any deployment starts.

---

## Deployment Modes

### Default Mode — Free Tier

Activated by running `infragen deploy` with no flags.

**Infrastructure for backend API (FastAPI / Flask / Django / Express):**
```
EC2 t3.micro          — runs the application (free tier: 750 hrs/month)
RDS db.t3.micro       — PostgreSQL in public subnet, SG-restricted (free tier: 750 hrs/month)
Security Group        — allows inbound on app port from internet, RDS only from EC2 SG
EBS 20GB              — root volume for EC2 (free tier: 30GB)
Elastic IP            — static public IP for EC2
SSM Parameters        — stores secrets and config (always free)
ECR                   — Docker image registry (500MB free tier)
Key Pair              — SSH access to EC2
```

**RDS placement in free tier:**
RDS is placed in a public subnet but its security group only allows connections on port 5432 (or 3306) from the EC2 instance's security group. It is not accessible from the public internet in practice. The approval gate shows a clear warning about this and explains that `--prod` puts RDS in a private subnet.

**Infrastructure for static frontend (React / Next.js static):**
```
S3 bucket             — stores built static files (5GB free tier)
CloudFront            — CDN distribution (1TB/month always free)
S3 bucket policy      — allows CloudFront OAC only, blocks all public access
```

Static frontend infrastructure is identical in both free and prod modes.

**Infrastructure for SSR frontend (Next.js SSR):**
```
EC2 t3.micro          — runs next start
Security Group        — allows inbound 3000 (or configured port)
Elastic IP
SSM Parameters
ECR
Key Pair
```
No RDS for SSR frontend. If the Next.js app calls a backend API, the backend URL is injected as `NEXT_PUBLIC_API_URL` environment variable.

**Estimated free tier cost:**
```
EC2 t3.micro    $0.00   (750 hrs/month, 12-month free tier)
RDS t3.micro    $0.00   (750 hrs/month, 12-month free tier)
EBS 20GB        $0.00   (30GB free tier)
S3              $0.00   (5GB free tier)
CloudFront      $0.00   (1TB always free)
Total           $0.00/month within free tier limits
After 12 months ~$33/month (EC2 ~$8 + RDS ~$25)
```

### Production Mode — `--prod` Flag

Activated by running `infragen deploy --prod`.

**Infrastructure for backend API:**
```
ECS Fargate           — runs containerized application (0.5 vCPU / 1GB default)
RDS db.t3.micro       — PostgreSQL in private subnet
ElastiCache           — Redis cache.t3.micro (only if Redis detected in codebase)
ALB                   — Application Load Balancer
VPC                   — dedicated VPC with public and private subnets
NAT Gateway           — allows private subnet outbound internet access
SSM Parameters        — secrets and config
ECR                   — Docker image registry
IAM roles             — ECS task execution role with least privilege
```

**Estimated production cost:**
```
ECS Fargate           $14.82/month
RDS db.t3.micro       $25.55/month
ElastiCache           $12.41/month  (only if Redis detected)
ALB                   $16.20/month
NAT Gateway           $32.40/month
ECR                   $1.00/month
Total                 ~$102/month
```

---

## Project Directory Structure

```
infragen/
│
├── cli/
│   ├── __init__.py
│   ├── main.py              — entry point, defines all Typer commands
│   ├── doctor.py            — infragen doctor command logic
│   └── prompts.py           — all Rich prompts, confirmations, secret input
│
├── scanner/
│   ├── __init__.py
│   ├── detector.py          — detects runtime, framework, service type
│   ├── dependencies.py      — parses requirements.txt / package.json for infra implications
│   ├── ports.py             — detects port from Dockerfile, source code, framework defaults
│   ├── env_vars.py          — scans .env.example, classifies vars as secret vs config
│   └── dockerfile.py        — parses existing Dockerfile or generates one from templates
│
├── agents/
│   ├── __init__.py
│   ├── orchestrator.py      — LangGraph graph, runs terraform_writer then security+cost in parallel
│   ├── terraform_writer.py  — generates all .tf files from InfraSpec
│   ├── security_auditor.py  — runs tfsec + checkov, uses LLM to synthesize findings
│   └── cost_estimator.py    — calls Infracost API, formats Rich table output
│
├── terraform/
│   ├── free/
│   │   ├── backend/
│   │   │   ├── main.tf.jinja
│   │   │   ├── variables.tf.jinja
│   │   │   ├── outputs.tf.jinja
│   │   │   └── security_groups.tf.jinja
│   │   └── frontend/
│   │       ├── main.tf.jinja
│   │       ├── variables.tf.jinja
│   │       └── outputs.tf.jinja
│   └── prod/
│       ├── backend/
│       │   ├── main.tf.jinja
│       │   ├── ecs.tf.jinja
│       │   ├── rds.tf.jinja
│       │   ├── vpc.tf.jinja
│       │   ├── alb.tf.jinja
│       │   ├── variables.tf.jinja
│       │   └── outputs.tf.jinja
│       └── frontend/
│           ├── main.tf.jinja       — same as free/frontend
│           ├── variables.tf.jinja
│           └── outputs.tf.jinja
│
├── docker_templates/
│   ├── fastapi.dockerfile
│   ├── flask.dockerfile
│   ├── django.dockerfile
│   ├── express.dockerfile
│   └── nextjs.dockerfile
│
├── deployer/
│   ├── __init__.py
│   ├── terraform.py         — runs terraform init, plan, apply, destroy via subprocess
│   ├── docker.py            — builds Docker image, pushes to ECR
│   └── static.py            — runs npm build, syncs to S3, invalidates CloudFront
│
├── prerequisites/
│   ├── __init__.py
│   ├── checker.py           — checks AWS CLI, Terraform, Docker are installed
│   └── permissions.py       — validates IAM permissions via policy simulation
│
├── models/
│   ├── __init__.py
│   ├── scan_result.py       — ScanResult dataclass
│   ├── infra_spec.py        — InfraSpec dataclass
│   └── enums.py             — Runtime, Framework, ServiceType, DeployMode enums
│
├── output/                  — generated at runtime, always gitignored
│   ├── terraform/           — generated .tf files written here
│   └── logs/                — deployment logs
│
├── pyproject.toml
├── README.md
└── .gitignore
```

---

## Data Flow

This is the complete flow from `infragen deploy` to deployed infrastructure.

```
1. User runs: infragen deploy (or infragen deploy --prod)

2. Prerequisites check (infragen doctor runs automatically)
   checker.py validates: AWS CLI, Terraform, Docker
   permissions.py validates: IAM permissions via policy simulation
   If anything fails → print specific fix instruction → exit

3. Scanner runs on current directory
   detector.py     → Runtime, Framework, ServiceType, Version
   dependencies.py → what AWS services are implied by dependencies
   ports.py        → what port the app listens on
   env_vars.py     → what env vars exist in .env.example and their classification
   dockerfile.py   → parse existing Dockerfile or flag that one will be generated
   
   Output: ScanResult dataclass

4. Conflict and inference display
   Show user what was detected
   Show what was inferred from code (Redis, S3, etc.) that they didn't mention
   Ask for confirmation on inferred resources
   Ask user to describe deployment in plain English
   If no Dockerfile: generate one, show it, ask for confirmation before proceeding

5. InfraSpec is built
   ScanResult + user's plain English description + mode (free/prod)
   → InfraSpec dataclass
   This is what all agents work from

6. Terraform Writer runs
   Reads InfraSpec
   Selects correct Jinja templates (free/prod × backend/frontend)
   Renders templates with InfraSpec values
   Writes .tf files to ./output/terraform/

7. Security Auditor and Cost Estimator run in parallel
   Both work on the .tf files written in step 6
   
   Security Auditor:
     subprocess: tfsec ./output/terraform/
     subprocess: checkov -d ./output/terraform/
     LLM (Groq): synthesize findings into plain English
     Classify each finding: auto-fixable vs needs user input
     Apply auto-fixes directly to the .tf files
   
   Cost Estimator:
     HTTP call to Infracost API with the .tf files
     Parse response
     Format as Rich table

8. Approval Gate displayed in terminal
   Section 1: DETECTED — what the scanner found
   Section 2: INFERRED — what was inferred from codebase
   Section 3: INFRASTRUCTURE PLAN — what will be created
   Section 4: SECURITY — findings, auto-fixes applied, items needing input
   Section 5: COST ESTIMATE — Rich table with per-resource cost
   Section 6: SECRETS — masked input for each secret variable
   Section 7: Final summary + "Deploy? (y/N)"
   
   If user types N → exit, nothing deployed, nothing charged
   If user types Y → proceed to step 9

9. Deployer runs
   For backend (free tier):
     docker.py: docker build → docker push to ECR
     terraform.py: terraform init → terraform plan → terraform apply
     Stream all output live to terminal using Rich Live
   
   For backend (prod):
     Same as free tier deployer
   
   For static frontend:
     static.py: npm run build → aws s3 sync → cloudfront invalidation
     terraform.py: terraform apply (for S3 bucket and CF distribution if first deploy)
   
   For SSR frontend:
     Same as backend deployer

10. Post-deployment output
    Print: endpoint URL (EC2 public IP, ALB DNS, or CloudFront URL)
    Print: useful next commands (infragen logs, infragen destroy)
    For backends: print SSH command and DB connection instructions
    Save state reference to ~/.infragen/state/<project-name>/
```

---

## Models — Exact Dataclass Definitions

### ScanResult

The output of the scanner. All fields populated by static analysis where possible, LLM only for ambiguous cases.

```python
@dataclass
class ScanResult:
    # Core detection
    runtime: Runtime                    # PYTHON or NODEJS
    framework: Framework                # FASTAPI, FLASK, DJANGO, EXPRESS, NEXTJS, REACT
    service_type: ServiceType           # BACKEND_API, FRONTEND_SSR, FRONTEND_STATIC
    runtime_version: str                # "3.11", "18", etc.
    port: int | None                    # None for static frontend
    has_dockerfile: bool

    # Dependency-inferred resources
    needs_rds: bool
    rds_engine: str | None              # "postgres" or "mysql"
    needs_elasticache: bool             # True if redis library detected
    needs_s3: bool                      # True if file upload library detected
    needs_ses: bool                     # True if email library detected
    needs_sticky_sessions: bool         # True if socket.io detected (prod only)

    # Env vars from .env.example
    env_vars: dict[str, str]            # {"DATABASE_URL": "config", "SECRET_KEY": "secret"}
    # "secret" → stored in SSM SecureString, user prompted for value
    # "config" → stored in SSM String or injected directly, user prompted if no default

    # Build info (frontend)
    build_command: str | None           # "npm run build"
    build_output_dir: str | None        # "build", "dist", "out"

    # Start command (backend)
    start_command: str | None           # "uvicorn main:app --host 0.0.0.0 --port 8000"

    # Django-specific
    django_project_name: str | None     # extracted from manage.py

    # Issues found during scan
    warnings: list[str]                 # non-blocking issues, shown to user
    # e.g. "gunicorn not in requirements.txt — will add automatically"

    # Things inferred from code not mentioned by user
    inferred_resources: list[str]
    # e.g. ["Redis (ioredis in package.json)", "S3 (multer in package.json)"]
```

### InfraSpec

Built from ScanResult + user's plain English description + deployment mode. Passed to all agents.

```python
@dataclass
class InfraSpec:
    # From ScanResult
    scan: ScanResult

    # From user input
    mode: DeployMode                    # FREE or PROD
    user_description: str               # raw plain English from user
    region: str                         # from aws configure or user input
    project_name: str                   # derived from directory name
    environment: str                    # "dev", "staging", "production"

    # Resolved from user description + scan
    instance_type: str                  # "t3.micro" (free) or from prod sizing
    rds_instance_class: str             # "db.t3.micro"
    
    # Confirmed inferred resources (after user says Y/N to each)
    confirmed_rds: bool
    confirmed_elasticache: bool         # prod only
    confirmed_s3: bool

    # Backend URL if deploying frontend
    backend_api_url: str | None

    # Output paths
    terraform_output_dir: Path          # ./output/terraform/
```

### Enums

```python
class Runtime(Enum):
    PYTHON = "python"
    NODEJS = "nodejs"

class Framework(Enum):
    FASTAPI  = "fastapi"
    FLASK    = "flask"
    DJANGO   = "django"
    EXPRESS  = "express"
    NEXTJS   = "nextjs"
    REACT    = "react"

class ServiceType(Enum):
    BACKEND_API      = "backend_api"
    FRONTEND_SSR     = "frontend_ssr"
    FRONTEND_STATIC  = "frontend_static"

class DeployMode(Enum):
    FREE = "free"
    PROD = "prod"
```

---

## Scanner — Detailed Rules

### Runtime Detection Priority

```
1. package.json exists AND (requirements.txt OR pyproject.toml exists)
   → read package.json dependencies
   → if next/react/express found → NODEJS
   → else → PYTHON

2. package.json only → NODEJS

3. requirements.txt / pyproject.toml / Pipfile only → PYTHON

4. Neither → DetectionError: "No package.json or requirements.txt found.
   Make sure you are running infragen from your project root."
```

### Framework Detection

**Node.js — check package.json dependencies and devDependencies:**
```
"next" in deps          → NEXTJS
"react" in deps         → REACT  (only if "next" not present)
"express" in deps       → EXPRESS
anything else           → UnsupportedFrameworkError
```

**Python — check requirements.txt (or pyproject.toml or Pipfile) content (case-insensitive):**
```
"fastapi" in content    → FASTAPI
"django" in content     → DJANGO  (check before flask, django includes flask-like patterns)
"flask" in content      → FLASK
anything else           → UnsupportedFrameworkError
```

### Next.js SSR vs Static Detection

```
Check for next.config.js, next.config.ts, next.config.mjs
If found:
  read content
  if "output" in content and "export" in content → FRONTEND_STATIC
  else → FRONTEND_SSR
If not found:
  → FRONTEND_SSR (default for Next.js)
```

### Port Detection Priority

```
1. Dockerfile EXPOSE directive          most reliable
2. .env.example PORT= value
3. Source code scan:
   Node.js: regex for app.listen(\d+) and server.listen(\d+)
   Python:  regex for uvicorn.run(.*port=\d+) and app.run(.*port=\d+)
4. Framework defaults (last resort):
   FastAPI  → 8000
   Flask    → 5000
   Django   → 8000
   Express  → 3000
   Next.js  → 3000
   React    → None (static, no port)
```

### Dependency → Infrastructure Mapping

Deterministic mapping, no LLM needed:

**Python (requirements.txt):**
```
psycopg2 / psycopg2-binary    → needs_rds=True, rds_engine="postgres"
PyMySQL / mysqlclient          → needs_rds=True, rds_engine="mysql"
redis / redis-py / aioredis    → needs_elasticache=True
boto3 / botocore               → note: user explicitly uses AWS SDK
django-storages                → needs_s3=True
Pillow + any upload indicator  → needs_s3=True (flag, not certain)
celery                         → flag: background worker detected
```

**Node.js (package.json):**
```
pg / postgres                  → needs_rds=True, rds_engine="postgres"
mysql2 / mysql                 → needs_rds=True, rds_engine="mysql"
ioredis / redis                → needs_elasticache=True
multer                         → needs_s3=True
@aws-sdk/client-s3             → needs_s3=True
socket.io                      → needs_sticky_sessions=True (prod only)
bull / bullmq                  → flag: job queue detected
nodemailer                     → needs_ses=True (flag)
```

### .env.example Classification

```
Key contains SECRET, KEY, PASSWORD, TOKEN, PRIVATE, CREDENTIAL, AUTH
  → classified as "secret" → SSM SecureString → user prompted for value at approval gate

Key contains URL, HOST, DATABASE, REDIS, ENDPOINT, BUCKET, PORT
  → classified as "config" → SSM String or injected directly

Key is NODE_ENV, DEBUG, ENVIRONMENT, APP_ENV
  → classified as "runtime_config" → set directly in EC2 user data or ECS task definition

Anything else
  → classified as "unknown" → treated as "config", flagged to user
```

### .env.example Requirement Enforcement

```
If .env.example not found:
  Check if .env exists:
    If yes:
      Print error:
        "No .env.example found.
         We found a .env file but will not read it (contains real secrets).
         Create .env.example with your variable names and empty values:
         
           DATABASE_URL=
           SECRET_KEY=
           REDIS_URL=
         
         Then run infragen deploy again."
      Exit.
    If no:
      Print error:
        "No .env.example found.
         Create one in your project root listing all environment variables
         your app needs, with empty values:
         
           DATABASE_URL=
           SECRET_KEY=
         
         Then run infragen deploy again."
      Exit.
```

### Dockerfile Handling

```
If Dockerfile found:
  Parse it:
    Extract EXPOSE port
    Check if runs as root (USER directive present?)
    Check if HEALTHCHECK present
    Extract base image
    Extract CMD
  Use it as-is for deployment
  Flag issues to security auditor (running as root, no healthcheck)

If Dockerfile not found:
  Generate one from docker_templates/<framework>.dockerfile
  Display the generated Dockerfile in full to the user in terminal
  Ask: "No Dockerfile found. Generated one for your <framework> app.
        Review it above. Use this Dockerfile? (y/N)
        Or add your own Dockerfile and run infragen deploy again."
  If N → exit
  If Y → write Dockerfile to project root, proceed
  Never silently use a generated Dockerfile
```

### Framework-Specific Scanner Notes

**Django:**
- Scan `manage.py` to extract project name (needed for gunicorn wsgi path)
- Pattern: `DJANGO_SETTINGS_MODULE`, `<project_name>.settings`
- If gunicorn not in requirements.txt → add it, warn user
- Start command: `gunicorn <project_name>.wsgi:application --bind 0.0.0.0:8000`
- Pre-deploy step: `python manage.py collectstatic --noinput`

**Flask:**
- If gunicorn not in requirements.txt → add it, warn user
- Start command: `gunicorn -w 4 -b 0.0.0.0:5000 app:app`
- Try to detect the Flask app variable name from source (default to `app`)

**FastAPI:**
- Start command: `uvicorn main:app --host 0.0.0.0 --port 8000`
- Try to detect module name and app variable from source (default to `main:app`)

**React:**
- Detect build tool: Vite (dist/) vs CRA (build/)
- Detect build command from package.json scripts.build
- No Dockerfile needed, no Docker required

**Next.js Static:**
- Build output is `out/` (next export)
- No Dockerfile needed
- Build command: `npm run build`

**Next.js SSR:**
- Needs Dockerfile
- Start command: `npm start` (runs next start)
- Build happens inside Dockerfile

---

## Agents — Detailed Behaviour

### LangGraph Graph Structure

```python
# Simplified graph definition
# The Terraform Writer runs first because Security Auditor
# and Cost Estimator both need the generated .tf files.

START
  → terraform_writer        (sequential — must finish before others start)
  → [security_auditor,      (parallel — both start simultaneously)
     cost_estimator]
  → approval_gate           (waits for both to finish)
  → END
```

### Terraform Writer Agent

**Input:** InfraSpec

**What it does:**
- Selects the correct template directory based on mode and service type
  - `terraform/free/backend/` for free tier backend
  - `terraform/free/frontend/` for free tier frontend
  - `terraform/prod/backend/` for prod backend
  - `terraform/prod/frontend/` for prod frontend (same as free)
- Renders Jinja templates with InfraSpec values
- Writes rendered files to `./output/terraform/`
- Does NOT call any AWS APIs — purely file generation

**What it generates (free tier backend):**
```
./output/terraform/
├── main.tf           — provider config, EC2 instance, RDS instance
├── variables.tf      — all variables with defaults
├── outputs.tf        — EC2 public IP, RDS endpoint
├── security_groups.tf — EC2 SG (app port open), RDS SG (only from EC2 SG)
├── ssm.tf            — SSM parameters for all env vars
├── ecr.tf            — ECR repository
├── key_pair.tf       — key pair for SSH
└── user_data.sh      — EC2 startup script (installs Docker, pulls image, runs container)
```

**What it generates (free tier frontend / prod frontend):**
```
./output/terraform/
├── main.tf           — S3 bucket, CloudFront distribution, OAC
├── variables.tf
└── outputs.tf        — CloudFront URL
```

**What it generates (prod backend):**
```
./output/terraform/
├── main.tf           — provider config
├── vpc.tf            — VPC, public subnets, private subnets, IGW, route tables
├── nat.tf            — NAT Gateway, EIP
├── ecs.tf            — ECS cluster, task definition, service
├── ecr.tf            — ECR repository
├── rds.tf            — RDS instance in private subnet
├── alb.tf            — ALB, target group, listener
├── elasticache.tf    — ElastiCache cluster (only if confirmed_elasticache=True)
├── iam.tf            — ECS task execution role and policy
├── security_groups.tf — ALB SG, ECS SG, RDS SG, ElastiCache SG
├── ssm.tf            — SSM parameters
├── variables.tf
└── outputs.tf        — ALB DNS name
```

**Key rules for Terraform generation:**
- All resources tagged with: `project_name`, `environment`, `managed_by = "infragen"`
- RDS in free tier: `publicly_accessible = true`, security group allows port only from EC2 SG
- RDS in prod: `publicly_accessible = false`, placed in private subnet
- All secrets go to SSM SecureString — never hardcoded in Terraform
- EC2 user data script: installs Docker, logs into ECR, pulls image, runs container with env vars injected from SSM
- Terraform state stored locally at `~/.infragen/state/<project-name>/terraform.tfstate`

### Security Auditor Agent

**Input:** Path to `./output/terraform/`

**What it does:**
1. Runs `tfsec ./output/terraform/` via subprocess, captures JSON output
2. Runs `checkov -d ./output/terraform/ --output json` via subprocess, captures JSON output
3. Merges findings from both tools, deduplicates overlapping findings
4. Uses Groq LLM to:
   - Explain each finding in plain English (not the raw tfsec/checkov message)
   - Classify: auto-fixable vs needs user input vs informational
5. Applies auto-fixes directly to the `.tf` files
6. Returns structured findings for display in approval gate

**Auto-fixable issues (applied silently, listed as "auto-fixed" in approval gate):**
- Dockerfile runs as root → add `USER appuser` to generated Dockerfile
- No HEALTHCHECK → add default healthcheck to generated Dockerfile
- RDS deletion protection disabled → add `deletion_protection = true`
- RDS backup retention not set → add `backup_retention_period = 7`
- S3 bucket versioning not enabled → enable versioning

**Needs user input (shown in approval gate, blocks deployment until resolved):**
- SSH open to 0.0.0.0/0 → ask user for their IP CIDR
- Any finding rated CRITICAL that cannot be auto-fixed

**Informational (shown but does not block):**
- Medium and low severity findings
- Best practice recommendations

### Cost Estimator Agent

**Input:** Path to `./output/terraform/`

**What it does:**
1. Calls Infracost API: `POST https://pricing.api.infracost.io/graphql`
   - Sends the Terraform files
   - Receives per-resource cost breakdown
2. Formats output as a Rich table with columns: Resource, Type, Monthly Cost
3. Adds a total row
4. Adds cost optimization tips if any resource costs more than 25% of total
   - NAT Gateway > 25% → suggest VPC endpoints for dev environments
   - RDS > 25% and it's t3.micro → note that reserved instances save 30%

**Fallback if Infracost API unavailable:**
Use hardcoded AWS pricing for the supported resource types. This is acceptable because infragen only deploys a small fixed set of resource types.

```python
HARDCODED_MONTHLY_PRICES = {
    "aws_instance.t3.micro":              8.47,
    "aws_db_instance.db.t3.micro":       25.55,
    "aws_elasticache_cluster.t3.micro":  12.41,
    "aws_lb":                            16.20,
    "aws_nat_gateway":                   32.40,
    "aws_ecr_repository":                 1.00,
    "aws_s3_bucket":                      0.023,  # per GB
    "aws_cloudfront_distribution":        0.00,   # within always-free tier
}
```

---

## CLI Commands — Complete Specification

### `infragen doctor`

Standalone prerequisite check. Also runs automatically at the start of every `infragen deploy`.

**Checks in order:**
1. AWS CLI installed (`aws --version`)
2. AWS credentials configured (`aws sts get-caller-identity`)
3. AWS region set (from `aws configure` or `AWS_DEFAULT_REGION` env var)
4. Terraform installed (`terraform --version`)
5. Docker installed and daemon running (`docker info`)
6. IAM permissions (policy simulation for each required action)

**Output format:**
```
Checking prerequisites...

  AWS CLI          ✓ installed (2.15.0)
  AWS credentials  ✓ configured
  AWS identity     ✓ arn:aws:iam::123456789:user/username
  AWS region       ✓ ap-south-1
  Terraform        ✓ installed (1.7.0)
  Docker           ✓ running

Checking AWS permissions...

  ec2:CreateVpc              ✓
  ecs:CreateCluster          ✓
  rds:CreateDBInstance       ✓
  ...

✓ All checks passed. Run infragen deploy inside your project folder.
```

On failure:
```
  Docker           ✗ not running
                     Start Docker Desktop and try again.
                     (Not required for React static deployments)

✗ 1 check failed. Fix the issue above and run infragen doctor again.
```

### `infragen deploy [--prod]`

Main command. Runs from inside a project directory.

**Full flow:**
```
1. Run infragen doctor (automatic)
2. Scan codebase
3. Display scan results, ask for confirmation on inferred resources
4. If no Dockerfile: generate, display, ask for confirmation
5. Ask user to describe deployment in plain English
6. Ask if frontend calls a backend API (if deploying frontend)
7. Build InfraSpec
8. Run agents (terraform writer → security auditor + cost estimator in parallel)
9. Display approval gate
10. Collect secret values
11. Ask "Deploy? (y/N)"
12. If Y: deploy and stream output
13. Print post-deployment summary
```

### `infragen destroy`

Tears down all infrastructure for the current project.

```
Reads: ~/.infragen/state/<project-name>/ to find Terraform state
Runs: terraform destroy
Asks for confirmation: "This will destroy all infrastructure for <project-name>. Type the project name to confirm: "
Streams: terraform destroy output live
Prints: "All infrastructure destroyed."
```

### `infragen logs`

Streams logs from running service to terminal.

```
Free tier:  streams CloudWatch logs for the EC2 instance (via SSM or CloudWatch agent)
Prod:       streams ECS service logs via CloudWatch Logs
```

### `infragen status`

Shows current state of deployed infrastructure.

```
Reads Terraform state to find resource IDs
Calls AWS APIs to get current health

Output:
  Service:    my-fastapi-app
  Status:     ✓ running
  Endpoint:   http://13.232.45.123:8000
  EC2:        i-0abc123 (t3.micro) — running
  RDS:        myapp-db.abc.ap-south-1.rds.amazonaws.com — available
  Uptime:     3 days, 4 hours
```

---

## Approval Gate — Full Terminal Display

This is exactly what the user sees before typing `y` or `n`. Every section is always shown. Sections with nothing to report still show with a "none" or checkmark.

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  infragen — deployment plan
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Mode:  FREE TIER  (run with --prod for production architecture)

DETECTED
  Runtime      Python 3.11
  Framework    FastAPI
  Type         Backend API
  Port         8000
  Dockerfile   Found

INFERRED FROM CODEBASE
  ✓ PostgreSQL   psycopg2 in requirements.txt
  ✓ Redis        redis-py in requirements.txt  [confirmed by user]
  - File uploads not detected

INFRASTRUCTURE PLAN
  EC2 t3.micro        1 instance (free tier)
  RDS db.t3.micro     PostgreSQL, public subnet, SG-restricted
  Security Groups     EC2 (port 8000 open), RDS (port 5432 from EC2 only)
  Elastic IP          1 static public IP
  ECR                 1 repository
  SSM Parameters      5 parameters (3 secrets, 2 config)
  Key Pair            infragen-<project-name>

  ⚠  RDS is in a public subnet (free tier limitation)
     It is only accessible from your EC2 instance via security group.
     Use --prod for private subnet deployment.

SECURITY
  ✓ auto-fixed   Dockerfile running as root — added non-root user
  ✓ auto-fixed   No HEALTHCHECK — added default healthcheck
  ✓ informational  RDS backup retention set to 7 days

COST ESTIMATE
  Resource                        Monthly
  ──────────────────────────────────────────
  EC2 t3.micro                    $0.00   (free tier)
  RDS db.t3.micro                 $0.00   (free tier)
  EBS 20GB gp2                    $0.00   (free tier)
  Elastic IP                      $0.00   (free when attached)
  ECR storage                     $0.00   (500MB free tier)
  SSM Standard Parameters         $0.00   (always free)
  ──────────────────────────────────────────
  Total                           $0.00 / month

  ⚠  Free tier applies to new AWS accounts for 12 months only
  ⚠  After free tier expires: ~$33/month

RESOURCES TO CREATE
  23 resources will be created in ap-south-1

SECRETS
  Enter values — sent directly to AWS SSM, never written to disk

  SECRET_KEY=         [hidden input]
  DATABASE_PASSWORD=  [hidden input]
  REDIS_URL=          [hidden input]

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Deploy? (y/N):
```

---

## Docker Templates

Each template is a production-ready Dockerfile for the framework. These are used when the user does not have a Dockerfile.

### fastapi.dockerfile
```dockerfile
FROM python:{version}-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE {port}

RUN adduser --disabled-password --gecos "" appuser
USER appuser

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:{port}/health')" || exit 1

CMD ["uvicorn", "{module}:app", "--host", "0.0.0.0", "--port", "{port}"]
```

### flask.dockerfile
```dockerfile
FROM python:{version}-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE {port}

RUN adduser --disabled-password --gecos "" appuser
USER appuser

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:{port}/')" || exit 1

CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:{port}", "{module}:app"]
```

### django.dockerfile
```dockerfile
FROM python:{version}-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN python manage.py collectstatic --noinput

EXPOSE {port}

RUN adduser --disabled-password --gecos "" appuser
USER appuser

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:{port}/')" || exit 1

CMD ["gunicorn", "{project_name}.wsgi:application", "--bind", "0.0.0.0:{port}"]
```

### express.dockerfile
```dockerfile
FROM node:{version}-alpine

WORKDIR /app

COPY package*.json ./
RUN npm ci --only=production

COPY . .

EXPOSE {port}

RUN addgroup -S appgroup && adduser -S appuser -G appgroup
USER appuser

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD node -e "require('http').get('http://localhost:{port}/health', (r) => process.exit(r.statusCode === 200 ? 0 : 1))" || exit 1

CMD ["node", "{entrypoint}"]
```

### nextjs.dockerfile
```dockerfile
FROM node:{version}-alpine AS builder

WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM node:{version}-alpine AS runner

WORKDIR /app
ENV NODE_ENV production

COPY --from=builder /app/.next ./.next
COPY --from=builder /app/public ./public
COPY --from=builder /app/package*.json ./
RUN npm ci --only=production

EXPOSE {port}

RUN addgroup -S appgroup && adduser -S appuser -G appgroup
USER appuser

CMD ["npm", "start"]
```

---

## Error Handling — Every Failure Mode

Every error must print a specific, actionable message. No stack traces shown to users (log them to `./output/logs/` but show a clean message).

```
DetectionError          — framework/runtime not detected
UnsupportedFrameworkError — framework detected but not supported
MissingEnvExampleError  — no .env.example found
AWSCredentialsError     — credentials not configured
InsufficientPermissionsError — missing IAM permissions
TerraformNotFoundError  — terraform not in PATH
DockerNotRunningError   — docker daemon not running
TerraformPlanError      — terraform plan failed (show terraform output)
TerraformApplyError     — terraform apply failed midway
  → triggers automatic: infragen destroy to clean up partial resources
DockerBuildError        — docker build failed
ECRPushError            — docker push to ECR failed
```

For `TerraformApplyError` specifically:
```
✗ Deployment failed during terraform apply.

  Error: <terraform error message>

  Cleaning up partial resources...
  Running terraform destroy... ✓

  All partial resources removed. No charges incurred.

  The error and full logs are saved to:
  ./output/logs/deploy-<timestamp>.log

  Common fixes:
  • Check your AWS account limits for this region
  • Verify your IAM permissions with: infragen doctor
```

---

## Python Dependencies

```toml
[tool.poetry.dependencies]
python       = "^3.11"
typer        = "^0.12"
rich         = "^13"
langgraph    = "^0.2"
langchain-groq = "^0.1"
boto3        = "^1.34"
python-hcl2  = "^4.3"
python-dotenv = "^1.0"
httpx        = "^0.27"
jinja2       = "^3.1"

[tool.poetry.dev-dependencies]
pytest       = "^8"
pytest-mock  = "^3"
```

---

## Environment Variables for infragen Itself

infragen needs these to run. Set once via `infragen init` or manually:

```
GROQ_API_KEY         — for LLM calls (security audit synthesis, ambiguous detection)
INFRACOST_API_KEY    — for cost estimation (free tier available at infracost.io)
```

These are stored in `~/.infragen/config` (not in the project being deployed).

---

## Build Order — Week by Week

### Week 1 — Scanner
Files: `models/`, `scanner/`

Goal: Given any supported project directory, produce a correct `ScanResult`.

Test: Run against real open source projects from GitHub for all 7 supported cases.
Do not proceed to Week 2 until scanner is correct for all 7 cases.

Testable with: `python -m scanner /path/to/project`

### Week 2 — Prerequisites and CLI Skeleton
Files: `prerequisites/`, `cli/`

Goal: `infragen doctor` works fully. `infragen deploy` runs doctor + scanner, prints result, exits with "coming soon".

Testable with: `infragen doctor` and `infragen deploy` from any project.

### Week 3 — Terraform Generation
Files: `agents/terraform_writer.py`, `terraform/`

Goal: Given a `ScanResult`, generate valid Terraform for all 7 cases.

Validate with: `terraform validate` and `terraform plan` (no AWS credentials needed).
Do not proceed until `terraform plan` runs cleanly for all 7 cases.

### Week 4 — Security Audit and Cost Estimation
Files: `agents/security_auditor.py`, `agents/cost_estimator.py`, `agents/orchestrator.py`

Goal: Full approval gate displayed in terminal with no actual deployment.

Testable with: `infragen deploy` — shows full approval gate, exits after `n`.

### Week 5 — Deployer
Files: `deployer/`

Goal: Actual deployment works for all 7 cases.

Also build: `infragen destroy`

### Week 6 — Polish
- `infragen logs`
- `infragen status`
- Edge cases and error handling
- Full end-to-end test for every framework
- README

---

## What a Good Demo Looks Like

```bash
# Terminal session 1 — deploy a FastAPI app (free tier, ~$0)
cd sample-fastapi-app
infragen deploy
# user sees: scan, inferred resources, approval gate with $0 cost, enters secrets, types y
# deployment streams live, ends with EC2 IP and connection commands

# Terminal session 2 — deploy a React app (free, always)
cd sample-react-app
infragen deploy
# user sees: scan, S3+CloudFront plan, $0 cost, types y
# npm build runs, S3 sync runs, CloudFront URL printed

# Show --prod flag
cd sample-fastapi-app
infragen deploy --prod
# approval gate shows ~$102/month cost, ECS + ALB + private RDS

# Clean up everything
infragen destroy
```

Total demo time: 5-8 minutes. Shows the full pipeline for two different frameworks and both deployment modes.

---

## Notes for Claude Code

- Start with Week 1. Do not write any AWS, Terraform, or agent code until the scanner is complete and tested.
- The scanner must handle the case where it cannot determine something — raise a specific error with a clear message rather than guessing.
- Every user-facing string should be written with care. The CLI is the entire product.
- `terraform plan` is free to run during development. Use it constantly to validate generated Terraform.
- Never read `.env`. Only `.env.example`. Enforce this strictly.
- The `output/` directory is always gitignored. Never commit generated Terraform or logs.
- Secrets entered by the user are stored only in AWS SSM. They are never written to any file.
- When in doubt about an infrastructure decision, use the free tier option.
