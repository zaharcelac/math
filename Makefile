# Docker image for the web app (see Dockerfile).
IMAGE ?= math-worksheets

.PHONY: build
build:
	docker build -t $(IMAGE) .
