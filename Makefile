.PHONY: install test init status

install:
	cd packages/cognition-engine && pip install -e ".[dev]"

test:
	cd packages/cognition-engine && python -m pytest tests/ -v

init:
	ce init --meta-tool --name "Cognition Engine"

status:
	ce status
