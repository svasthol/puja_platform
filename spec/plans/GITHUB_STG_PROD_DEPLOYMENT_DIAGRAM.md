# GitHub → staging → production deployment (diagrams)

**Repo:** `svasthol/puja_platform`  
**Procedure:** [`DEVELOPER_RELEASE_FLOW.md`](./DEVELOPER_RELEASE_FLOW.md) · **Gates:** [`STG_TO_PROD_PIPELINE.md`](./STG_TO_PROD_PIPELINE.md)

Legend: **solid** = operational today · **dashed** = planned before prod cut

---

## 1. End-to-end (branches, Actions, environments)

```mermaid
flowchart TB
  subgraph DEV_MACHINE["Developer laptop"]
    CODE["Edit + commit"]
    PUSH_DEV["git push origin dev"]
    PR_MAIN["PR: dev → main\n(release promotion)"]
  end

  subgraph GITHUB["GitHub (puja_platform)"]
    BR_DEV[("branch: dev")]
    BR_MAIN[("branch: main")]
    WF_CI["Workflow: CI\nci.yml"]
    WF_STG["Workflow: Deploy staging\ndeploy-staging.yml"]
    WF_SMOKE["Manual: storage / db-verify / redis"]
    WF_BUILD["Workflow: build-push\n(planned)"]
    WF_PROD["Workflow: Deploy production\ndeploy-prod.yml"]
    ENV_STG{{"Environment: staging"}}
    ENV_PROD{{"Environment: production\n+ approval"}}
  end

  subgraph STG_OCI["OCI staging — stg-aio-1"]
    RUNNER["Self-hosted runner\noptional"]
    VM["VM: API :8000\nAdmin :3000\nPostgres + Celery"]
    APIENV["/etc/mana-guruji/api.env\nSTAGING_CONFIG_ROLLOUT"]
  end

  subgraph PROD_OCI["OCI production — planned"]
    OCIR[("OCIR hyd.ocir.io\nimage digest")]
    APP1["app-1 / app-2"]
    NLB["NLB + TLS"]
    VAULT["Vault / Ansible env"]
  end

  CODE --> PUSH_DEV --> BR_DEV
  BR_DEV --> WF_CI
  BR_DEV --> WF_STG
  WF_STG --> ENV_STG
  ENV_STG -->|SSH or self-hosted| VM
  RUNNER -.->|runs jobs on VM| WF_STG
  APIENV --> VM
  WF_SMOKE -.->|manual smoke| VM

  BR_DEV --> PR_MAIN --> BR_MAIN
  BR_MAIN --> WF_CI
  BR_MAIN -.-> WF_BUILD
  WF_BUILD -.-> OCIR

  BR_MAIN -.->|STG-GATE passed| WF_PROD
  WF_PROD -.-> ENV_PROD
  ENV_PROD -.->|same SHA or digest| APP1
  OCIR -.-> APP1
  VAULT -.-> APP1
  APP1 -.-> NLB
```

---

## 2. Sequence — daily path (code to staging)

```mermaid
sequenceDiagram
  autonumber
  participant Dev as Developer
  participant GH as GitHub
  participant CI as ci.yml
  participant DS as deploy-staging.yml
  participant VM as stg-aio-1

  Dev->>GH: push commit to dev
  GH->>CI: run (arm64 runtime + preflight)
  CI-->>GH: pass / fail
  alt app paths changed or manual dispatch
    GH->>DS: run (environment staging)
    DS->>VM: remote_staging_deploy.sh
    Note over VM: git pull dev, pip, migrate,<br/>restart api/worker/beat, admin build
    DS->>VM: health curl :8000 / :3000
    DS-->>GH: job result
  end
  Dev->>VM: optional api.env + verify scripts
  Note over VM: Config phases STG-CFG-*<br/>not in git
```

---

## 3. Sequence — promotion to prod (target)

```mermaid
sequenceDiagram
  autonumber
  participant Dev as Release owner
  participant GH as GitHub
  participant STG as Staging proof
  participant MAIN as branch main
  participant BP as build-push (planned)
  participant DP as deploy-prod (planned)
  participant PRD as Prod fleet

  Dev->>STG: health, VAL-*, STG-CFG-*, incidents review
  STG-->>Dev: STG-GATE OK
  Dev->>GH: PR merge dev → main
  GH->>MAIN: release SHA pinned
  Dev->>GH: manual smokes on main (storage, db-verify)
  GH->>BP: build arm64 → OCIR
  BP-->>GH: image digest
  GH->>DP: deploy-prod (approval)
  DP->>PRD: migrate DB role, rolling restart,<br/>digest pin — no SSH git pull
  DP-->>GH: smoke + health
```

---

## 4. What runs where (workflow map)

```mermaid
flowchart LR
  subgraph Triggers
    T1["push dev\n(app paths)"]
    T2["workflow_dispatch"]
    T3["PR / push main"]
    T4["merge + STG-GATE"]
  end

  subgraph Workflows
    W1["ci.yml"]
    W2["deploy-staging.yml"]
    W3["staging-storage-smoke.yml"]
    W4["db-verify.yml"]
    W5["redis-ensure-staging.yml"]
    W6["deploy-prod.yml"]
    W7["build-push.yml"]
  end

  subgraph Target
    S["stg-aio-1"]
    P["app-1 / app-2"]
  end

  T1 --> W1
  T1 --> W2
  T3 --> W1
  T2 --> W2
  T2 --> W3
  T2 --> W4
  T2 --> W5
  T2 --> W6
  T4 -.-> W7
  T4 -.-> W6

  W1 --> S
  W2 --> S
  W3 --> S
  W4 --> S
  W5 --> S
  W6 -.-> P
  W7 -.-> P
```

---

## 5. Config vs code (two parallel tracks)

```mermaid
flowchart TB
  subgraph CODE_TRACK["Track A — application code"]
    C1["commit"] --> C2["push dev"]
    C2 --> C3["Deploy staging"]
    C3 --> C4["VM runs git SHA from dev"]
  end

  subgraph CONFIG_TRACK["Track B — staging secrets & URLs"]
    K1["edit api.env / admin.env on VM"]
    K2["restart systemd units"]
    K3["verify_staging_storage / bootstrap_catalog / …"]
    K1 --> K2 --> K3
  end

  C4 --> LIVE["Staging live behavior"]
  K3 --> LIVE

  subgraph PROD_TRACK["Prod readiness — same code, different env"]
    P1["Vault + deploy/env examples"]
    P2["Prove on staging first"]
    P2 --> P1
    P1 -.-> PLIVE["Prod behavior"]
    C4 -.->|promote SHA via main| PLIVE
  end
```

---

## 6. Branch & environment cheat sheet

| Artifact | `dev` | `main` | Staging VM | Prod (planned) |
|----------|-------|--------|------------|----------------|
| Default integration | ✓ push daily | ✗ no direct feature work | tracks **`origin/dev`** | tracks **digest / pinned SHA** |
| **ci.yml** | push / PR | push / PR | — | — |
| **deploy-staging.yml** | auto + manual | manual only if dispatched | deploy target | — |
| **deploy-prod.yml** | — | preflight / future deploy | — | **app-1/2** |
| Secrets for deploy | — | — | `api.env` on VM + GH **staging** env | GH **production** + Vault |
| New Actions in sidebar | if YAML on default branch | **main** lists workflows | runner labels | prod runners TBD |

---

*Render diagrams in GitHub, VS Code (Mermaid), or Cursor markdown preview. Last updated: 2026-10-24*
