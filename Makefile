APP := app.main:app
PORT ?= 8001

.PHONY: dev test run docker docker-run

dev:            ## local dev server with auto-reload
	pip install -q -r requirements-dev.txt
	uvicorn $(APP) --host 0.0.0.0 --port $(PORT) --reload

test:           ## full test suite
	python -m pytest tests/ -q

run:            ## production-style local run
	pip install -q -r requirements.txt
	uvicorn $(APP) --host 0.0.0.0 --port $(PORT)

docker:         ## build the image
	docker build -t carecap .

docker-run:     ## run the image (demo state resets each boot; -v a dir for persistence)
	docker run --rm -p $(PORT):8001 -v carecap-data:/srv/data carecap
