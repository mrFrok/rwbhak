.PHONY: test report seed breakeven analytics

test:
	python -m pytest -q

report:
	python -m scripts.build_report

seed:
	python -m data.seed

breakeven:
	python -m core.breakeven

analytics:
	python -m scripts.build_report && python -m scripts.build_analytics
