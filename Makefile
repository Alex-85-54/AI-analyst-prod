PROFILE?=''

up:
	docker compose --profile $(PROFILE) up --watch

down:
	docker compose down
