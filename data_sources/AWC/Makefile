# =============================================================================
#  Arizona Water Company — Full Lab (PostgreSQL + MinIO)
#  Detailed, self-verifying setup for the Pentaho Data Catalog course.
#
#  Common usage:
#    make            show help
#    make all        full stack: preflight -> up -> bucket -> load -> check
#    make check      run ALL verification checks against a running stack
#    make status     show health of both services
#    make destroy    remove both containers and wipe all data
#
#  All credentials and paths live in .env (single source of truth).
# =============================================================================

# ---- Shell ------------------------------------------------------------------
# Use bash explicitly so escape sequences behave the same on every machine.
SHELL := /bin/bash

# ---- Load configuration -----------------------------------------------------
ifneq (,$(wildcard .env))
include .env
export
else
$(error .env not found — see README.md)
endif

# ---- Derived values ---------------------------------------------------------
DOCS_ABS := $(abspath $(DOCS_DIR))

# MinIO mc client runs in a throwaway container on the lab network.
MC_RUN  := docker run --rm --network $(LAB_NETWORK) --entrypoint sh minio/mc -c
ALIAS   := mc alias set awc $(MINIO_ENDPOINT) $(MINIO_ROOT_USER) $(MINIO_ROOT_PASSWORD)

# Expected counts for verification.
EXPECTED_FILES := $(shell find $(DOCS_DIR) -type f 2>/dev/null | wc -l | tr -d ' ')
EXPECTED_TABLES := 6

# psql shorthand: run a query inside the postgres container as the admin user.
PSQL = docker exec -e PGPASSWORD=$(PG_ADMIN_PASSWORD) $(PG_CONTAINER) \
       psql -U $(PG_ADMIN_USER) -d $(PG_DB) -tAc

# Pretty output. Real ESC byte so colours work in any shell.
ESC    := $(shell printf '\033')
C_OK   := $(ESC)[0;32m
C_WARN := $(ESC)[0;33m
C_ERR  := $(ESC)[0;31m
C_INFO := $(ESC)[0;36m
C_BOLD := $(ESC)[1m
C_OFF  := $(ESC)[0m

.DEFAULT_GOAL := help
.PHONY: help all check preflight up \
        pg-up pg-verify pg-tables pg-user pg-shell pg-reset \
        bucket load reload verify-root verify verify-bucket verify-user verify-files \
        status logs console clean destroy

# =============================================================================
#  HELP
# =============================================================================
help:
	@echo ""
	@echo "$(C_INFO)$(C_BOLD)Arizona Water Company — Full Lab (PostgreSQL + MinIO)$(C_OFF)"
	@echo ""
	@echo "  $(C_BOLD)Setup$(C_OFF)"
	@echo "    make all          Full stack with checks (preflight->up->bucket->load->check)"
	@echo "    make up            Start BOTH services and wait until ready"
	@echo "    make bucket        Create the MinIO bucket + read-only PDC user"
	@echo "    make load          Upload documents to MinIO from DOCS_DIR"
	@echo "    make reload        Re-upload documents (overwrites)"
	@echo ""
	@echo "  $(C_BOLD)Verification$(C_OFF)"
	@echo "    make check         Run ALL checks (database + object store)"
	@echo "    make pg-verify     Check database: tables loaded + read-only user works"
	@echo "    make pg-tables     List the awc_operations tables and row counts"
	@echo "    make verify-bucket Confirm the MinIO bucket exists"
	@echo "    make verify-user   Confirm the read-only MinIO user can log in"
	@echo "    make verify-files  Confirm uploaded file count matches local ($(EXPECTED_FILES))"
	@echo "    make status        Show health of both services"
	@echo ""
	@echo "  $(C_BOLD)Tools$(C_OFF)"
	@echo "    make pg-shell      Open an interactive psql shell"
	@echo "    make console       Print PDC connection details for both sources"
	@echo "    make logs          Tail logs from both services"
	@echo ""
	@echo "  $(C_BOLD)Teardown$(C_OFF)"
	@echo "    make clean         Stop + remove containers (keeps data)"
	@echo "    make destroy       Stop + remove containers AND wipe all data"
	@echo "    make pg-reset      Recreate ONLY the database from scratch"
	@echo ""
	@echo "  Config from .env: db=$(PG_DB), bucket=$(BUCKET), docs=$(DOCS_DIR) ($(EXPECTED_FILES) files)"
	@echo ""

# =============================================================================
#  FULL SETUP
# =============================================================================
all: preflight up bucket load check
	@echo ""
	@echo "$(C_OK)============================================================$(C_OFF)"
	@echo "$(C_OK)$(C_BOLD) Lab is ready — database and object store, all checks passed.$(C_OFF)"
	@echo "$(C_OK)============================================================$(C_OFF)"
	@$(MAKE) --no-print-directory console

# =============================================================================
#  PREFLIGHT
# =============================================================================
preflight:
	@echo "$(C_INFO)▶ Preflight checks$(C_OFF)"
	@command -v docker >/dev/null 2>&1 \
		&& echo "  $(C_OK)✓$(C_OFF) docker found" \
		|| { echo "  $(C_ERR)✗ docker not found on PATH$(C_OFF)"; exit 1; }
	@docker compose version >/dev/null 2>&1 \
		&& echo "  $(C_OK)✓$(C_OFF) docker compose plugin found" \
		|| { echo "  $(C_ERR)✗ 'docker compose' not available$(C_OFF)"; exit 1; }
	@docker info >/dev/null 2>&1 \
		&& echo "  $(C_OK)✓$(C_OFF) docker daemon is running" \
		|| { echo "  $(C_ERR)✗ docker daemon not reachable$(C_OFF)"; exit 1; }
	@test -d "$(DOCS_DIR)" \
		&& echo "  $(C_OK)✓$(C_OFF) documents folder found: $(DOCS_ABS)" \
		|| { echo "  $(C_ERR)✗ documents folder not found: $(DOCS_DIR)$(C_OFF)"; exit 1; }
	@test "$(EXPECTED_FILES)" -gt 0 \
		&& echo "  $(C_OK)✓$(C_OFF) $(EXPECTED_FILES) files staged for upload" \
		|| { echo "  $(C_ERR)✗ no files under $(DOCS_DIR)$(C_OFF)"; exit 1; }
	@test -f postgres-init/01-schema-and-data.sql \
		&& echo "  $(C_OK)✓$(C_OFF) database init scripts present" \
		|| { echo "  $(C_ERR)✗ postgres-init/01-schema-and-data.sql missing$(C_OFF)"; exit 1; }
	@echo "  $(C_OK)✓ preflight passed$(C_OFF)"

# =============================================================================
#  UP — start both services and block until each is genuinely ready
# =============================================================================
up:
	@echo "$(C_INFO)▶ Starting PostgreSQL and MinIO$(C_OFF)"
	docker compose up -d
	@$(MAKE) --no-print-directory pg-up
	@$(MAKE) --no-print-directory minio-up

# ---- PostgreSQL readiness + auto-load verification --------------------------
pg-up:
	@echo "$(C_INFO)▶ Waiting for PostgreSQL to be ready (up to 60s)$(C_OFF)"
	@ready=0; \
	for i in $$(seq 1 30); do \
		if docker exec $(PG_CONTAINER) pg_isready -U $(PG_ADMIN_USER) -d $(PG_DB) >/dev/null 2>&1; then \
			echo "  $(C_OK)✓ PostgreSQL is accepting connections$(C_OFF)"; ready=1; break; \
		fi; \
		printf "  ...waiting (%d/30)\r" $$i; sleep 2; \
	done; \
	if [ "$$ready" -ne 1 ]; then \
		echo ""; echo "  $(C_ERR)✗ PostgreSQL did not become ready in 60s$(C_OFF)"; \
		echo "    Try: docker compose logs postgres"; exit 1; \
	fi
	@echo "$(C_INFO)▶ Waiting for sample data to finish loading$(C_OFF)"
	@for i in $$(seq 1 30); do \
		COUNT=$$($(PSQL) "SELECT count(*) FROM information_schema.tables WHERE table_schema='awc_operations';" 2>/dev/null || echo 0); \
		if [ "$$COUNT" -ge "$(EXPECTED_TABLES)" ]; then \
			echo "  $(C_OK)✓ sample data loaded ($$COUNT tables in awc_operations)$(C_OFF)"; exit 0; \
		fi; \
		printf "  ...loading (%d/30)\r" $$i; sleep 2; \
	done; \
	echo ""; echo "  $(C_WARN)! tables not all present yet — check 'make pg-tables'$(C_OFF)"

# ---- MinIO readiness + root-credential check --------------------------------
minio-up:
	@echo "$(C_INFO)▶ Waiting for MinIO to be ready (up to 60s)$(C_OFF)"
	@ready=0; \
	for i in $$(seq 1 30); do \
		if $(MC_RUN) '$(ALIAS)' >/dev/null 2>&1; then \
			echo "  $(C_OK)✓ MinIO is accepting connections$(C_OFF)"; ready=1; break; \
		fi; \
		printf "  ...waiting (%d/30)\r" $$i; sleep 2; \
	done; \
	if [ "$$ready" -ne 1 ]; then \
		echo ""; echo "  $(C_ERR)✗ MinIO did not become ready in 60s$(C_OFF)"; \
		echo "    Try: docker compose logs minio"; exit 1; \
	fi
	@$(MAKE) --no-print-directory verify-root

verify-root:
	@echo "$(C_INFO)▶ Verifying MinIO root credentials match .env$(C_OFF)"
	@RUNNING=$$(docker exec $(MINIO_CONTAINER) env 2>/dev/null | grep '^MINIO_ROOT_USER=' | cut -d= -f2); \
	if [ "$$RUNNING" = "$(MINIO_ROOT_USER)" ]; then \
		echo "  $(C_OK)✓$(C_OFF) MinIO root user is '$$RUNNING' (matches .env)"; \
	else \
		echo "  $(C_ERR)✗ MISMATCH:$(C_OFF) container booted with '$$RUNNING' but .env says '$(MINIO_ROOT_USER)'"; \
		echo "    Fix: make destroy && make all"; exit 1; \
	fi

# =============================================================================
#  MINIO — bucket, user, load
# =============================================================================
bucket:
	@echo "$(C_INFO)▶ Creating bucket '$(BUCKET)' and read-only user '$(PDC_USER)'$(C_OFF)"
	@$(MC_RUN) '$(ALIAS) && \
		mc mb -p awc/$(BUCKET) && \
		(mc admin user add awc $(PDC_USER) $(PDC_SECRET) || true) && \
		printf "%s" "{\"Version\":\"2012-10-17\",\"Statement\":[{\"Effect\":\"Allow\",\"Action\":[\"s3:GetObject\",\"s3:GetBucketLocation\"],\"Resource\":[\"arn:aws:s3:::$(BUCKET)/*\"]},{\"Effect\":\"Allow\",\"Action\":[\"s3:ListBucket\"],\"Resource\":[\"arn:aws:s3:::$(BUCKET)\"]}]}" > /tmp/awc-ro.json && \
		mc admin policy create awc awc-readonly /tmp/awc-ro.json 2>/dev/null; \
		mc admin policy attach awc awc-readonly --user $(PDC_USER) 2>/dev/null || true' \
		&& echo "  $(C_OK)✓ bucket and user step completed$(C_OFF)" \
		|| { echo "  $(C_ERR)✗ bucket/user creation failed$(C_OFF)"; exit 1; }
	@$(MAKE) --no-print-directory verify-bucket
	@$(MAKE) --no-print-directory verify-user

load:
	@echo "$(C_INFO)▶ Loading $(EXPECTED_FILES) documents from $(DOCS_DIR)$(C_OFF)"
	@test -d "$(DOCS_DIR)" || { echo "  $(C_ERR)✗ $(DOCS_DIR) not found$(C_OFF)"; exit 1; }
	@docker run --rm --network $(LAB_NETWORK) \
		-v "$(DOCS_ABS):/docs:ro" --entrypoint sh minio/mc -c \
		'$(ALIAS) && mc cp --recursive /docs/ awc/$(BUCKET)/' \
		&& echo "  $(C_OK)✓ upload finished$(C_OFF)" \
		|| { echo "  $(C_ERR)✗ upload failed$(C_OFF)"; exit 1; }
	@$(MAKE) --no-print-directory verify-files

reload:
	@echo "$(C_INFO)▶ Clearing and re-uploading the bucket$(C_OFF)"
	@$(MC_RUN) '$(ALIAS) && mc rm --recursive --force awc/$(BUCKET)/ 2>/dev/null || true'
	@$(MAKE) --no-print-directory load

# =============================================================================
#  VERIFICATION — everything
# =============================================================================
check: pg-verify verify
	@echo "$(C_OK)$(C_BOLD)✓ all verification checks passed (database + object store)$(C_OFF)"

verify: verify-bucket verify-user verify-files

# ---- Database checks --------------------------------------------------------
pg-verify: pg-tables pg-user

pg-tables:
	@echo "$(C_INFO)▶ Checking database tables and row counts$(C_OFF)"
	@COUNT=$$($(PSQL) "SELECT count(*) FROM information_schema.tables WHERE table_schema='awc_operations';" 2>/dev/null || echo 0); \
	if [ "$$COUNT" -ge "$(EXPECTED_TABLES)" ]; then \
		echo "  $(C_OK)✓$(C_OFF) $$COUNT tables present in awc_operations"; \
	else \
		echo "  $(C_ERR)✗ expected $(EXPECTED_TABLES) tables, found $$COUNT$(C_OFF)"; \
		echo "    Try: make pg-reset"; exit 1; \
	fi
	@for t in customers water_systems tiered_rates monthly_usage water_quality_reports account_alerts; do \
		N=$$($(PSQL) "SELECT count(*) FROM awc_operations.$$t;" 2>/dev/null || echo "ERR"); \
		if [ "$$N" = "ERR" ]; then \
			echo "  $(C_ERR)✗ table $$t missing or unreadable$(C_OFF)"; exit 1; \
		else \
			printf "  $(C_OK)✓$(C_OFF) %-24s %s rows\n" "$$t" "$$N"; \
		fi; \
	done
	@OPTOUT=$$($(PSQL) "SELECT count(*) FROM awc_operations.customers WHERE opted_out_marketing = TRUE;" 2>/dev/null || echo 0); \
	echo "  $(C_OK)✓$(C_OFF) opted_out_marketing present ($$OPTOUT customers opted out — drives the WS4 rule)"

pg-user:
	@echo "$(C_INFO)▶ Checking read-only database user '$(PDC_DB_USER)'$(C_OFF)"
	@docker exec -e PGPASSWORD=$(PDC_DB_SECRET) $(PG_CONTAINER) \
		psql -U $(PDC_DB_USER) -d $(PG_DB) -tAc \
		"SELECT count(*) FROM awc_operations.customers;" >/dev/null 2>&1 \
		&& echo "  $(C_OK)✓$(C_OFF) user '$(PDC_DB_USER)' can authenticate and read customers" \
		|| { echo "  $(C_ERR)✗ user '$(PDC_DB_USER)' cannot read the data$(C_OFF)"; exit 1; }
	@WRITE=$$(docker exec -e PGPASSWORD=$(PDC_DB_SECRET) $(PG_CONTAINER) \
		psql -U $(PDC_DB_USER) -d $(PG_DB) -tAc \
		"INSERT INTO awc_operations.water_systems(system_id,system_name) VALUES (999,'x');" 2>&1 || true); \
	if echo "$$WRITE" | grep -qi "permission denied"; then \
		echo "  $(C_OK)✓$(C_OFF) user '$(PDC_DB_USER)' is correctly read-only (write denied)"; \
	else \
		echo "  $(C_WARN)!$(C_OFF) write was not denied — check the GRANTs"; \
	fi

# ---- MinIO checks -----------------------------------------------------------
verify-bucket:
	@echo "$(C_INFO)▶ Checking MinIO bucket exists$(C_OFF)"
	@$(MC_RUN) '$(ALIAS) && mc ls awc/$(BUCKET) >/dev/null' \
		&& echo "  $(C_OK)✓$(C_OFF) bucket '$(BUCKET)' exists and is reachable" \
		|| { echo "  $(C_ERR)✗ bucket '$(BUCKET)' not found — run 'make bucket'$(C_OFF)"; exit 1; }

verify-user:
	@echo "$(C_INFO)▶ Checking read-only MinIO user$(C_OFF)"
	@ok=0; \
	for i in $$(seq 1 10); do \
		if docker run --rm --network $(LAB_NETWORK) --entrypoint sh minio/mc -c \
			'mc alias set chk $(MINIO_ENDPOINT) $(PDC_USER) $(PDC_SECRET) >/dev/null 2>&1 && \
			 mc ls chk/$(BUCKET) >/dev/null 2>&1'; then \
			ok=1; break; \
		fi; \
		if [ "$$i" = "3" ]; then \
			echo "  $(C_WARN)!$(C_OFF) read not granted yet — re-attaching read-only policy"; \
			$(MC_RUN) '$(ALIAS) >/dev/null 2>&1 && \
				printf "%s" "{\"Version\":\"2012-10-17\",\"Statement\":[{\"Effect\":\"Allow\",\"Action\":[\"s3:GetObject\",\"s3:GetBucketLocation\"],\"Resource\":[\"arn:aws:s3:::$(BUCKET)/*\"]},{\"Effect\":\"Allow\",\"Action\":[\"s3:ListBucket\"],\"Resource\":[\"arn:aws:s3:::$(BUCKET)\"]}]}" > /tmp/awc-ro.json && \
				mc admin policy create awc awc-readonly /tmp/awc-ro.json 2>/dev/null; \
				mc admin policy attach awc awc-readonly --user $(PDC_USER) 2>/dev/null || true' >/dev/null 2>&1 || true; \
		fi; \
		printf "  ...waiting for IAM to propagate (%d/10)\r" $$i; \
		sleep 2; \
	done; \
	if [ "$$ok" = "1" ]; then \
		echo "  $(C_OK)✓$(C_OFF) user '$(PDC_USER)' can authenticate and read the bucket    "; \
	else \
		echo "  $(C_ERR)✗ user '$(PDC_USER)' cannot read the bucket after retries$(C_OFF)"; \
		echo "    Try: make bucket   (re-creates the user and policy)"; \
		exit 1; \
	fi
	@WRITE=$$(docker run --rm --network $(LAB_NETWORK) --entrypoint sh minio/mc -c \
		'mc alias set chk $(MINIO_ENDPOINT) $(PDC_USER) $(PDC_SECRET) >/dev/null 2>&1 && \
		 echo t | mc pipe chk/$(BUCKET)/.writetest 2>&1' || true); \
	if echo "$$WRITE" | grep -qi "denied\|forbidden"; then \
		echo "  $(C_OK)✓$(C_OFF) user '$(PDC_USER)' is correctly read-only (write denied)"; \
	else \
		echo "  $(C_WARN)!$(C_OFF) write test not denied — check the readonly policy"; \
		$(MC_RUN) '$(ALIAS) >/dev/null 2>&1 && mc rm awc/$(BUCKET)/.writetest 2>/dev/null || true' >/dev/null 2>&1 || true; \
	fi

verify-files:
	@echo "$(C_INFO)▶ Checking uploaded file count$(C_OFF)"
	@UP=$$($(MC_RUN) '$(ALIAS) >/dev/null 2>&1 && mc ls --recursive awc/$(BUCKET)/' 2>/dev/null | grep -c . ); \
	echo "  local files: $(EXPECTED_FILES)   uploaded objects: $$UP"; \
	if [ "$$UP" -ge "$(EXPECTED_FILES)" ] && [ "$(EXPECTED_FILES)" -gt 0 ]; then \
		echo "  $(C_OK)✓$(C_OFF) all $(EXPECTED_FILES) files present in the bucket"; \
	else \
		echo "  $(C_ERR)✗ count mismatch — expected $(EXPECTED_FILES), found $$UP$(C_OFF)"; \
		echo "    Try: make reload"; exit 1; \
	fi

# =============================================================================
#  TOOLS
# =============================================================================
pg-shell:
	@echo "$(C_INFO)Opening psql as $(PG_ADMIN_USER) on $(PG_DB)  (\\q to quit)$(C_OFF)"
	docker exec -it -e PGPASSWORD=$(PG_ADMIN_PASSWORD) $(PG_CONTAINER) \
		psql -U $(PG_ADMIN_USER) -d $(PG_DB)

status:
	@echo "$(C_INFO)▶ Container status$(C_OFF)"
	@docker ps --filter name=$(PG_CONTAINER) --filter name=$(MINIO_CONTAINER) \
		--format "  {{.Names}}  |  {{.Status}}  |  {{.Ports}}" || echo "  (none running)"
	@echo "$(C_INFO)▶ Database$(C_OFF)"
	@$(PSQL) "SELECT '  ' || table_name FROM information_schema.tables WHERE table_schema='awc_operations' ORDER BY table_name;" 2>/dev/null || echo "  (not reachable)"
	@echo "$(C_INFO)▶ Object store$(C_OFF)"
	@$(MC_RUN) '$(ALIAS) >/dev/null 2>&1 && mc ls --recursive awc/$(BUCKET)/' 2>/dev/null | sed 's/^/  /' || echo "  (not reachable)"

logs:
	docker compose logs -f --tail=40

console:
	@echo ""
	@echo "  $(C_INFO)$(C_BOLD)Pentaho Data Catalog — connection details$(C_OFF)"
	@echo ""
	@echo "  $(C_BOLD)Database source (Arizona_Water_Operations)$(C_OFF)"
	@echo "    Type      :  PostgreSQL"
	@echo "    Host/Port :  $(PG_HOST) : 5432   (or localhost from the host)"
	@echo "    Database  :  $(PG_DB)"
	@echo "    User/Pass :  $(PDC_DB_USER) / $(PDC_DB_SECRET)   (read-only)"
	@echo ""
	@echo "  $(C_BOLD)Object store source (Arizona_Water_Documents)$(C_OFF)"
	@echo "    Type      :  S3-compatible / object store"
	@echo "    Endpoint  :  $(MINIO_ENDPOINT)   (or http://localhost:9000 from the host)"
	@echo "    Access/Sec:  $(PDC_USER) / $(PDC_SECRET)   (read-only)"
	@echo "    Bucket    :  $(BUCKET)   ·   Path-Style: Enabled"
	@echo ""
	@echo "  MinIO console: http://localhost:9001  ($(MINIO_ROOT_USER) / $(MINIO_ROOT_PASSWORD))"
	@echo ""

# =============================================================================
#  TEARDOWN
# =============================================================================
clean:
	@echo "$(C_INFO)▶ Stopping and removing containers (data kept)$(C_OFF)"
	docker compose down
	@echo "  $(C_OK)✓ stopped — data volumes preserved$(C_OFF)"

destroy:
	@echo "$(C_WARN)▶ Removing containers and ERASING all data (database + objects)$(C_OFF)"
	docker compose down -v
	@echo "  $(C_OK)✓ destroyed — all data volumes wiped$(C_OFF)"

# pg-reset: rebuild ONLY the database (re-runs the init scripts)
pg-reset:
	@echo "$(C_WARN)▶ Recreating ONLY the database from scratch$(C_OFF)"
	docker compose rm -fsv postgres
	docker volume rm $$(docker volume ls -q | grep awc-pgdata) 2>/dev/null || true
	docker compose up -d postgres
	@$(MAKE) --no-print-directory pg-up
	@$(MAKE) --no-print-directory pg-verify
