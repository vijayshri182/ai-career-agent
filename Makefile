# AI Career Agent — Development Commands

.PHONY: help install dev infra start test lint format audit clean

help:
	@echo "Available commands:"
	@echo "  make install   Install Python dependencies"
	@echo "  make dev       Install dev dependencies"
	@echo "  make infra     Start local infrastructure (db, redis, minio)"
	@echo "  make stop      Stop local infrastructure"
	@echo "  make test      Run tests"
	@echo "  make lint      Run linters"
	@echo "  make format    Format code"
	@echo "  make audit     Run dependency/security audit"
	@echo "  make clean     Clean build artifacts"

install:
	pip install -e .

dev:
	pip install -e ".[dev]"

infra:
	docker-compose up -d db redis minio

stop:
	docker-compose down

test:
	pytest

lint:
	ruff check src tests
	mypy src

format:
	ruff format src tests

audit:
	pip-audit

clean:
	rm -rf build dist *.egg-info .pytest_cache .mypy_cache .ruff_cache htmlcov
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
