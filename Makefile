.PHONY: help install init-db generate seed kpis test dashboard clean

help:
	@echo "TapRebook — common commands"
	@echo ""
	@echo "  make install      Install Python dependencies"
	@echo "  make generate     Generate synthetic sample data CSVs (~90 days, 3 clinics)"
	@echo "  make init-db      Create SQLite DB, apply schema + views, load sample data"
	@echo "  make kpis         Run all KPI queries and print results"
	@echo "  make ab-test      Run A/B test analysis (reminder cadence)"
	@echo "  make dashboard    Launch Streamlit KPI dashboard"
	@echo "  make test         Run pytest"
	@echo "  make clean        Remove generated DB and caches"

install:
	pip install -r requirements.txt

generate:
	python -m taprebook.data_gen.generate

init-db:
	python scripts/init_db.py

kpis:
	python scripts/run_all_kpis.py

ab-test:
	python -m taprebook.experiments.ab_reminder_cadence

dashboard:
	streamlit run dashboards/streamlit_app.py

test:
	pytest -v

clean:
	rm -rf data/taprebook.db
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type d -name .pytest_cache -exec rm -rf {} +
