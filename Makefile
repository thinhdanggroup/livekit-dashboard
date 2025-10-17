.PHONY: help install run dev test fmt lint clean docker-build docker-run docker-stop docker-logs

# Default target
.DEFAULT_GOAL := help

# Colors for output
BLUE := \033[0;34m
GREEN := \033[0;32m
YELLOW := \033[0;33m
NC := \033[0m # No Color

help: ## Show this help message
	@echo "$(BLUE)LiveKit Dashboard - Available Commands$(NC)"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(GREEN)%-15s$(NC) %s\n", $$1, $$2}'

install: ## Install dependencies using Poetry
	@echo "$(BLUE)Installing dependencies...$(NC)"
	poetry install

run: ## Run the application in production mode
	@echo "$(BLUE)Starting LiveKit Dashboard...$(NC)"
	poetry run uvicorn app.main:app --host 0.0.0.0 --port 8000

dev: ## Run the application in development mode with auto-reload
	@echo "$(BLUE)Starting LiveKit Dashboard in development mode...$(NC)"
	poetry run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

test: ## Run tests with pytest
	@echo "$(BLUE)Running tests...$(NC)"
	poetry run pytest -v

test-cov: ## Run tests with coverage report
	@echo "$(BLUE)Running tests with coverage...$(NC)"
	poetry run pytest --cov=app --cov-report=html --cov-report=term

fmt: ## Format code with Black
	@echo "$(BLUE)Formatting code...$(NC)"
	poetry run black app/

lint: ## Lint code with Ruff and mypy
	@echo "$(BLUE)Linting code...$(NC)"
	poetry run ruff check app/
	@echo "$(BLUE)Type checking...$(NC)"
	poetry run mypy app/

clean: ## Clean up cache and temporary files
	@echo "$(BLUE)Cleaning up...$(NC)"
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "htmlcov" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name ".coverage" -delete
	@echo "$(GREEN)Cleanup complete!$(NC)"

docker-build: ## Build Docker image
	@echo "$(BLUE)Building Docker image...$(NC)"
	docker build -t livekit-dashboard:latest .

docker-run: ## Run application using Docker Compose
	@echo "$(BLUE)Starting LiveKit Dashboard with Docker Compose...$(NC)"
	docker-compose up -d
	@echo "$(GREEN)Dashboard is running at http://localhost:8000$(NC)"

docker-stop: ## Stop Docker Compose services
	@echo "$(BLUE)Stopping Docker services...$(NC)"
	docker-compose down

docker-logs: ## View Docker Compose logs
	docker-compose logs -f

docker-shell: ## Open a shell in the running container
	docker-compose exec dashboard /bin/bash

env-example: ## Create .env file from .env.example
	@if [ ! -f .env ]; then \
		echo "$(BLUE)Creating .env file...$(NC)"; \
		echo "# LiveKit Server Configuration" > .env; \
		echo "LIVEKIT_URL=http://localhost:7880" >> .env; \
		echo "LIVEKIT_API_KEY=your-api-key" >> .env; \
		echo "LIVEKIT_API_SECRET=your-api-secret" >> .env; \
		echo "" >> .env; \
		echo "# Admin Authentication" >> .env; \
		echo "ADMIN_USERNAME=admin" >> .env; \
		echo "ADMIN_PASSWORD=changeme" >> .env; \
		echo "" >> .env; \
		echo "# Application Settings" >> .env; \
		echo "APP_SECRET_KEY=$$(openssl rand -hex 32)" >> .env; \
		echo "DEBUG=false" >> .env; \
		echo "HOST=0.0.0.0" >> .env; \
		echo "PORT=8000" >> .env; \
		echo "" >> .env; \
		echo "# Feature Flags" >> .env; \
		echo "ENABLE_SIP=false" >> .env; \
		echo "$(GREEN).env file created!$(NC)"; \
	else \
		echo "$(YELLOW).env file already exists$(NC)"; \
	fi

setup: install env-example ## Initial setup: install dependencies and create .env
	@echo "$(GREEN)Setup complete! Edit .env with your LiveKit credentials, then run 'make dev'$(NC)"

check: lint test ## Run all checks (lint + test)
	@echo "$(GREEN)All checks passed!$(NC)"

server-up:
	@poetry run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload