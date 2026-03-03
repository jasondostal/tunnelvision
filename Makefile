.PHONY: build dev up down logs shell test clean

# Build the production image
build:
	docker build -t tunnelvision:latest .

# Start development environment
dev:
	docker compose -f docker-compose.dev.yml up --build

# Start production environment
up:
	docker compose up -d

# Stop all containers
down:
	docker compose down

# View logs
logs:
	docker compose logs -f tunnelvision

# Shell into the running container
shell:
	docker exec -it tunnelvision /bin/bash

# Run health check
health:
	@curl -s http://localhost:8081/api/v1/health | jq .

# Check VPN status
status:
	@curl -s http://localhost:8081/api/v1/vpn/status | jq .

# Check public IP
ip:
	@curl -s http://localhost:8081/api/v1/vpn/ip | jq .

# Clean build artifacts and runtime data
clean:
	docker compose down -v
	rm -rf config/ downloads/
	docker rmi tunnelvision:latest 2>/dev/null || true

# Multi-arch build and push
release:
	docker buildx build \
		--platform linux/amd64,linux/arm64 \
		-t ghcr.io/jasondostal/tunnelvision:latest \
		--push .
