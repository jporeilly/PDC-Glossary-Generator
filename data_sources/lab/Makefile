# =============================================================================
#  PDC demo lab — SHARED PostgreSQL + MinIO for all scenarios
#
#  Common usage:
#    make              show help
#    make up           start the shared stack and wait until ready
#    make load SCENARIO=CSCU     load a scenario (db + schema + bucket + docs)
#    make remove SCENARIO=AWC    drop a scenario's database + bucket
#    make status       containers, databases and buckets at a glance
#    make console      print PDC connection details per loaded scenario
#    make destroy      remove containers and wipe ALL data
#
#  All credentials live in .env (single source of truth).
# =============================================================================
SHELL := /bin/bash

ifneq (,$(wildcard .env))
include .env
export
else
$(error .env not found — cp .env.example .env first)
endif

MC_RUN := docker run --rm --network $(LAB_NETWORK) --entrypoint sh minio/mc -c
ALIAS  := mc alias set lab $(MINIO_ENDPOINT) $(MINIO_ROOT_USER) $(MINIO_ROOT_PASSWORD)
PSQL    = docker exec -e PGPASSWORD=$(PG_ADMIN_PASSWORD) $(PG_CONTAINER) \
          psql -U $(PG_ADMIN_USER) -d postgres -tAc

ESC    := $(shell printf '\033')
C_OK   := $(ESC)[0;32m
C_ERR  := $(ESC)[0;31m
C_INFO := $(ESC)[0;36m
C_BOLD := $(ESC)[1m
C_OFF  := $(ESC)[0m

.DEFAULT_GOAL := help
.PHONY: help up preflight load remove status console logs clean destroy

help:
	@echo ""
	@echo "$(C_INFO)$(C_BOLD)PDC demo lab — shared PostgreSQL + MinIO (all scenarios)$(C_OFF)"
	@echo ""
	@echo "    make up                    Start the shared stack, wait until ready"
	@echo "    make load SCENARIO=CSCU    Load a scenario into it (repeatable per scenario)"
	@echo "    make remove SCENARIO=AWC   Drop that scenario's database + bucket"
	@echo "    make status                Containers, databases, buckets"
	@echo "    make console               PDC connection details per loaded scenario"
	@echo "    make logs                  Tail logs from both services"
	@echo "    make clean                 Stop containers (data kept)"
	@echo "    make destroy               Stop containers AND wipe all data"
	@echo ""
	@echo "  Scenarios available:"
	@bash ./load-scenario.sh | sed -n 's/^    /    /p'
	@echo ""

preflight:
	@command -v docker >/dev/null 2>&1 || { echo "$(C_ERR)✗ docker not found$(C_OFF)"; exit 1; }
	@docker compose version >/dev/null 2>&1 || { echo "$(C_ERR)✗ docker compose plugin missing$(C_OFF)"; exit 1; }
	@docker info >/dev/null 2>&1 || { echo "$(C_ERR)✗ docker daemon not reachable$(C_OFF)"; exit 1; }
	@echo "  $(C_OK)✓ preflight passed$(C_OFF)"

up: preflight
	@echo "$(C_INFO)▶ Starting shared PostgreSQL and MinIO$(C_OFF)"
	docker compose up -d
	@echo "$(C_INFO)▶ Waiting for PostgreSQL (up to 60s)$(C_OFF)"
	@for i in $$(seq 1 30); do \
		if docker exec $(PG_CONTAINER) pg_isready -U $(PG_ADMIN_USER) -d postgres >/dev/null 2>&1; then \
			echo "  $(C_OK)✓ PostgreSQL ready$(C_OFF)"; break; fi; \
		[ $$i -eq 30 ] && { echo "  $(C_ERR)✗ PostgreSQL not ready$(C_OFF)"; exit 1; }; \
		printf "  ...waiting (%d/30)\r" $$i; sleep 2; done
	@echo "$(C_INFO)▶ Waiting for MinIO (up to 60s)$(C_OFF)"
	@for i in $$(seq 1 30); do \
		if $(MC_RUN) '$(ALIAS)' >/dev/null 2>&1; then \
			echo "  $(C_OK)✓ MinIO ready$(C_OFF)"; break; fi; \
		[ $$i -eq 30 ] && { echo "  $(C_ERR)✗ MinIO not ready$(C_OFF)"; exit 1; }; \
		printf "  ...waiting (%d/30)\r" $$i; sleep 2; done
	@echo ""
	@echo "  Next: make load SCENARIO=CSCU   (and/or RETAIL, HEALTH)"

load:
	@test -n "$(SCENARIO)" || { echo "usage: make load SCENARIO=<ID>"; exit 1; }
	@bash ./load-scenario.sh $(SCENARIO)

remove:
	@test -n "$(SCENARIO)" || { echo "usage: make remove SCENARIO=<ID>"; exit 1; }
	@bash ./load-scenario.sh --remove $(SCENARIO)

status:
	@echo "$(C_INFO)▶ Containers$(C_OFF)"
	@docker ps --filter name=$(PG_CONTAINER) --filter name=$(MINIO_CONTAINER) \
		--format "  {{.Names}}  |  {{.Status}}  |  {{.Ports}}" || echo "  (none running)"
	@echo "$(C_INFO)▶ Databases$(C_OFF)"
	@$(PSQL) "SELECT '  ' || datname FROM pg_database WHERE datistemplate=false AND datname<>'postgres' ORDER BY datname;" 2>/dev/null || echo "  (not reachable)"
	@echo "$(C_INFO)▶ Buckets$(C_OFF)"
	@$(MC_RUN) '$(ALIAS) >/dev/null 2>&1 && mc ls lab/' 2>/dev/null | sed 's/^/  /' || echo "  (not reachable)"

console:
	@echo ""
	@echo "  $(C_INFO)$(C_BOLD)PDC demo lab — connection details (shared stack)$(C_OFF)"
	@echo ""
	@echo "  PostgreSQL:  <VM-IP>:$(PG_PORT)   (in-network only: $(PG_CONTAINER):5432)"
	@echo "  MinIO S3:    http://<VM-IP>:$(MINIO_PORT)   (in-network only: $(MINIO_ENDPOINT))"
	@echo "  MinIO console: http://<VM-IP>:$(MINIO_CONSOLE_PORT)  ($(MINIO_ROOT_USER) / $(MINIO_ROOT_PASSWORD))"
	@echo ""
	@for m in ../*/scenario.json; do \
		id=$$(basename $$(dirname $$m)); \
		db=$$(python3 -c "import json;print(json.load(open('$$m')).get('database',''))" 2>/dev/null); \
		bucket=$$(python3 -c "import json;print(json.load(open('$$m')).get('bucket',''))" 2>/dev/null); \
		muser=$$(python3 -c "import json;print(json.load(open('$$m')).get('minio_user',''))" 2>/dev/null); \
		loaded=$$($(PSQL) "SELECT 1 FROM pg_database WHERE datname='$$db'" 2>/dev/null); \
		state=$$([ "$$loaded" = "1" ] && echo "LOADED" || echo "not loaded"); \
		echo "  $(C_BOLD)$$id$(C_OFF) [$$state]  db $$db (pdc_user / catalog123!)  ·  bucket $$bucket ($$muser / $(PDC_MINIO_SECRET))"; \
	done
	@echo ""

logs:
	docker compose logs -f --tail=40

clean:
	docker compose down
	@echo "  $(C_OK)✓ stopped — data volumes preserved$(C_OFF)"

destroy:
	@echo "$(C_ERR)▶ Removing containers and ERASING all scenario data$(C_OFF)"
	docker compose down -v
	@echo "  $(C_OK)✓ destroyed$(C_OFF)"
