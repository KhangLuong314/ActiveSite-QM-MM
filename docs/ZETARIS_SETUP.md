# Zetaris Integration & DataScout Setup Guide

This document records the exact investigation into how Zetaris and the DataScout catalog run on this machine, how access credentials were obtained, the adapter table query results, and how teammates can reproduce the local data layer.

---

## 0. Verified setup (26 Oct 2026, Sidd's Mac): read this first

Sections 1 and 2 below record the earlier investigation, when no team machine had Zetaris. This is what works now.

1. **Get the platform.** Sign in to Zetaris Cloud Gateway (email one-time code). It is a launcher only: the dashboard shows 0 computes until you start one. Choose **Run locally** (free). Skip "Set up on AWS" (it creates resources billed to your own AWS account).
2. **Docker resources.** 8 GB memory, 4+ CPUs and Rosetta (the images are amd64). On Colima: `colima start --cpu 6 --memory 8 --vm-type vz --vz-rosetta`. The bundle's `./preflight.sh` needs the `docker compose` plugin.
3. **Registry login.** Run the `docker login zetarishackathon.azurecr.io -u ... --password-stdin` command from the Run locally page in your own terminal (it carries a password; do not paste it into chats or logs).
4. **Start.** In the unzipped `zetaris-platform` folder: `docker compose pull`, `docker compose up -d`, then `./verify.sh` until all checks pass (first start under emulation takes about 5 to 10 minutes). Web UI on `http://localhost:3000`, REST on `http://localhost:8888/api/v1.0`, JDBC on `localhost:10000`.
5. **Load our tables.** From this repo: `scripts/zetaris/load.sh <path-to-zetaris-platform>`. It exports `expert_runs` (lab expert QM regions), `eda_synthetic` (SYNTHETIC placeholder) and `rcsb_entries` to CSV and registers them as `ACTIVESITE.*` Lightning filestore tables.
6. **Configure `.env`.** `ZETARIS_REST_URL=http://localhost:8888/api/v1.0`, `ZETARIS_USER` and `ZETARIS_PASSWORD` = the platform admin login (in the bundle's own `.env`), `ZETARIS_ORG_ID=1`, and the three `ZETARIS_TABLE_*` names from `.env.example`.
7. **Check.** `uv run python smoke_test.py` gives 3/3 PASS (REST line: `ACTIVESITE.expert_runs: 6 rows`). `uv run python run.py --case ippoi_site_a --json` shows `"catalog": "zetaris"` and Jaccard 1.0.

**API facts learned the hard way**
- SQL goes to `POST /api/v1.0/query/sql/start` with `{"select": "...", "pageLimit": 1..100}` and headers `Authorization: Bearer <token>`, `X-Org-ID`, `X-Request-ID` (UUID). `/sql-editor/sqls/run` exists but needs a different body; the adapter no longer uses it.
- The token is the `idToken` from `GET /api/v1.0/auth/login` (HTTP Basic, with `X-Org-ID` and `X-Request-ID`). It expires; the adapter logs in again once on a 401.
- Every value comes back as a string. The adapter converts `qmcharge`, `total` and `resolution` back to numbers.
- The query API accepts SELECT only. DDL (`CREATE LIGHTNING ...`) runs through `bin/lightning-sql.sh` in a one-off `bootstrap` container; inside the live `driver` container it hangs at the metastore step.
- A first registration attempt that hung left a table named `lab_runs` unusable, which is why the table is called `expert_runs`.

 (Environment Audit)

### Docker Inspection
```bash
docker ps -a
```
**Output:**
```text
CONTAINER ID   IMAGE                           COMMAND                  CREATED      STATUS                PORTS                                 NAMES
812eb926fd5c   postgres:16-alpine              "docker-entrypoint.s…"   7 days ago   Up 7 days (healthy)   127.0.0.1:56432->5432/tcp             activesite-local-postgres-1
07fbcbb98e2d   bitnamilegacy/minio:2025.4.22   "/opt/bitnami/script…"   7 days ago   Up 7 days             9001/tcp, 127.0.0.1:59100->9000/tcp   activesite-local-minio-1
```

### Port Listener Check (Ports 3000 & 8888)
```bash
lsof -nP -iTCP:3000 -sTCP:LISTEN
lsof -nP -iTCP:8888 -sTCP:LISTEN
```
* **Port 3000:** No listener active (exit code 1).
* **Port 8888:** No listener active (exit code 1).

### Compose File Used
* **Location:** `docker-compose.yml` (in project root)
* **Services Defined:**
  * `postgres` (`postgres:16-alpine`): Bound to `127.0.0.1:56432:5432`
  * `minio` (`bitnamilegacy/minio:2025.4.22`): Bound to `127.0.0.1:59100:9000`
* **Zetaris Containers:** Neither the Zetaris web console (port 3000) nor the Zetaris query engine (port 8888) runs as a local Docker container in this repository.

### SSH Tunnels & Port-Forwards
* Checked running processes via `ps aux | grep -iE "(zetaris|tunnel|ssh)"`.
* No active SSH tunnel, `kubectl port-forward`, or remote port-forwarding process is running to redirect port 3000 or 8888 to a hosted Zetaris instance.

### Conclusion on Connectivity
Zetaris does **not** run locally on this machine. When `.env` configures `ZETARIS_BASE_URL=http://localhost:3000` and `ZETARIS_REST_URL=http://localhost:8888/api/v1.0`, direct connection attempts to ports 3000 and 8888 result in `Connection Refused`. The system works seamlessly on this machine because ActiveSite's `FallbackAdapter` (`activesite/adapters/zetaris.py`) automatically intercepts the connection failure and routes queries to `catalog-STANDIN (DuckDB)`.

---

## 2. Obtaining Zetaris Credentials (`ZETARIS_API_KEY` & `ZETARIS_ORG_ID`)

> [!WARNING]
> **Claim Steps Status: Unverified**
> The self-service account claim and sign-up steps below are **unverified** unless verified against the specific kickoff email or official GenAI Works HackOS portal page.

### Portal / Account Registration (Unverified)
1. **Hackathon Portal Registration:** Log in to the GenAI Works HackOS participant platform.
2. **Sponsor Claim Link:** Navigate to the Hackathon Resources / Sponsor Tools section and click the Zetaris Hobby Tier participant claim link (or follow the link in the official kickoff announcement email).
3. **Account Creation:** Sign up for the Zetaris sandbox environment (e.g. `cloud.enterprise.zetaris.com/register`).
4. **Organization ID (`ZETARIS_ORG_ID`):** Once logged into the Zetaris Console, the Org ID is listed under **Account / Workspace Settings** (default for hackathon sandbox workspaces is `1`).
5. **API Key (`ZETARIS_API_KEY`):**
   * Navigate to **User Profile -> Settings -> API Keys / Access Tokens**.
   * Generate a new personal access token (`ak...`).
6. **Environment Configuration:** Place the credentials into `.env`:
   ```bash
   ZETARIS_BASE_URL=http://localhost:3000
   ZETARIS_REST_URL=http://localhost:8888/api/v1.0
   ZETARIS_ORG_ID=1
   ZETARIS_API_KEY=<your-zetaris-api-token>
   ```

### Zetaris Freemium Repository & Private Container Images
For running Zetaris locally in Docker Compose:
* **Freemium Repository:** [github.com/zetaris/Freemium](https://github.com/zetaris/Freemium)
* **Container Images:** `zetaris/lightning-*:v2.4.1.0-latest` (including `zetaris/lightning-api:v2.4.1.0-latest`)
* **Access Requirements:** The images are hosted in a **private** repository on Docker Hub. Pulling them requires an approved Docker Hub account that has been granted access by the Zetaris team (`docker login` required; unauthenticated inspect/pull commands fail with `denied: requested access to the resource is denied` / `unauthorized: authentication required`).


---

## 3. DataScout Adapter Table Query Verification

### Execution Command
```bash
uv run python -c "from dotenv import load_dotenv; load_dotenv('.env', override=True); from activesite.adapters.zetaris import get_adapter; a=get_adapter(); print(a.label); [print(k, len(a.run_sql(q))) for k,q in {'lab_runs':f\"SELECT * FROM {a.tables['lab_runs']} LIMIT 5\", 'eda':f\"SELECT * FROM {a.tables['eda']} LIMIT 5\", 'pdb':f\"SELECT * FROM {a.tables['pdb']} LIMIT 5\"}.items()]"
```

### Output
```text
catalog-STANDIN (DuckDB) (Zetaris unreachable: ConnectError)
lab_runs 5
eda 3
pdb 0
```

### Table Breakdown & Status
1. **Adapter Label:** `catalog-STANDIN (DuckDB) (Zetaris unreachable: ConnectError)`
   * The adapter is not `"zetaris"` because `http://localhost:8888/api/v1.0` is not listening, triggering an automatic fallback to DuckDB.
2. **`lab_runs` (5 rows returned):** Served via DuckDB attached to local Postgres (`pg.public.lab_runs` on port 56432). Contains reference expert masks, charges, and case IDs.
3. **`eda` (3 rows returned):** Served via DuckDB over `s3://activesite/eda/eda_synthetic.parquet` in local MinIO (port 59100).
4. **`pdb` (0 rows returned):** The `rcsb_entries` table is populated dynamically when `adapter.prepare(case)` is invoked by the orchestrator for a specific system (e.g. `ippoi_wt`). In a standalone query without `prepare()`, the table schema exists but contains 0 rows.

### How to Load `lab_runs` into Zetaris from `seed/seed.py:lab_rows()`
If a live remote Zetaris cluster endpoint is available:
1. **Via PostgreSQL Data Source Registration:**
   * In the Zetaris Console, go to **Data Sources -> Add New Source -> PostgreSQL**.
   * Provide the connection credentials to the Postgres database running `activesite-local-postgres-1`.
   * Register the `lab_runs` table. Zetaris will federate queries directly to it.
2. **Via Zetaris REST DDL Execution:**
   * Run a script that extracts rows from `seed.seed.lab_rows()`:
     ```python
     from seed.seed import lab_rows
     rows = lab_rows()
     ```
   * Post DDL to `${ZETARIS_REST_URL}/sql-editor/sqls/run`:
     ```sql
     CREATE TABLE lab_runs (
       case_id VARCHAR PRIMARY KEY,
       system VARCHAR,
       site VARCHAR,
       qmmask VARCHAR,
       qmcharge INTEGER,
       residues VARCHAR,
       source VARCHAR,
       status VARCHAR
     );
     ```
   * Insert the rows using parameterized `INSERT INTO lab_runs VALUES (...)`.

---

## 4. Teammate Reproduction Steps

To reproduce the working data layer on another machine:

1. **Start the local database containers:**
   ```bash
   docker compose up -d
   ```
   *Verifies `postgres` on port `56432` and `minio` on port `59100`.*

2. **Sync Python environment:**
   ```bash
   uv sync
   ```

3. **Seed the local stand-in database:**
   ```bash
   uv run python seed/seed.py
   ```
   *Seeds 6 benchmark rows into Postgres `lab_runs` and uploads `eda_synthetic.parquet` to MinIO.*

4. **Verify the data adapter:**
   ```bash
   uv run python -c "from activesite.adapters.zetaris import get_adapter; a=get_adapter(); print(a.label); [print(k, len(a.run_sql(q))) for k,q in {'lab_runs':f\"SELECT * FROM {a.tables['lab_runs']} LIMIT 5\", 'eda':f\"SELECT * FROM {a.tables['eda']} LIMIT 5\"}.items()]"
   ```
   *Expected: `catalog-STANDIN (DuckDB)` with 5 rows from `lab_runs` and 3 rows from `eda`.*

---

## 5. Verification Outputs

### 1. `smoke_test.py`
```bash
uv run python smoke_test.py
```
**Output:**
```text
FAIL Data (Zetaris Web UI) HTTPConnectionPool(host='localhost', port=3000): Max retries exceeded with url: / (Caused by NewConnectionError("HTTPConnection(host='localhost', port=3000): Failed to establish a new connection: [Errno 61] Connection refused"))
FAIL Data (Zetaris REST API) HTTPConnectionPool(host='localhost', port=8888): Max retries exceeded with url: /api/v1.0/sql-editor/sqls/run (Caused by NewConnectionError("HTTPConnection(host='localhost', port=8888): Failed to establish a new connection: [Errno 61] Connection refused"))
PASS Power (NVIDIA Nemotron)
```

### 2. Sample Mode Benchmark Run (`ippoi_site_a`)
```bash
SAMPLE_MODE=true uv run python run.py --case ippoi_site_a --json
```
**Output (Redacted to Target Fields):**
```json
{
  "catalog": "catalog-STANDIN (DuckDB) (Zetaris unreachable: ConnectError)",
  "validation": {
    "jaccard": 1.0
  }
}
```
*(Full run succeeded in 2.98s, achieving atom Jaccard 1.0 against the expert mask using reference data from `lab_runs`).*
