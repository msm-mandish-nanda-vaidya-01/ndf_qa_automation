.DEFAULT_GOAL := help
PYTHON  ?= python
PYTEST  ?= $(PYTHON) -m pytest
ENV     ?= dev
SUB     ?= subsidiary_001
DATA    ?= test

.PHONY: help install install-hooks lint format test test-module test-etl test-login \
        test-e2e test-critical report report-open clean

help:  ## show this help
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

install:  ## install deps + playwright browsers
	$(PYTHON) -m pip install -r requirements.txt
	$(PYTHON) -m playwright install --with-deps chromium

install-hooks:  ## install pre-commit hooks
	$(PYTHON) -m pre_commit install

lint:  ## ruff + black/isort check (no writes)
	$(PYTHON) -m ruff check lib
	$(PYTHON) -m black --check lib
	$(PYTHON) -m isort --check-only lib

format:  ## autoformat
	$(PYTHON) -m isort lib
	$(PYTHON) -m black lib
	$(PYTHON) -m ruff check --fix lib

test:  ## run everything
	$(PYTEST)

test-module:  ## run one module: make test-module M=etl/gdb
	$(PYTEST) lib/app/modules/$(M)

test-etl:  ## etl/gdb module flow
	$(PYTEST) -m module lib/app/modules/etl/gdb

test-login:  ## purchase_checker/login module flow
	$(PYTEST) -m module lib/app/modules/purchase_checker/login

test-e2e:  ## cross-module end-to-end
	$(PYTEST) -m e2e lib/app/e2e

test-critical:  ## critical-path smoke
	$(PYTEST) -m critical_path lib/app/critical_path

cli:  ## run the CLI entrypoint: make cli ARGS="--suite e2e"
	$(PYTHON) -m lib.app.main.main --env $(ENV) --subsidiary $(SUB) --data-set $(DATA) $(ARGS)

report:  ## generate the allure static site
	allure generate reports/allure-results -o reports/allure-report --clean

report-open:  ## generate + open allure
	$(MAKE) report
	allure open reports/allure-report

clean:  ## drop caches and run output
	rm -rf .pytest_cache .ruff_cache .mypy_cache
	rm -rf reports/allure-results/* reports/allure-report/* logs/*
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
