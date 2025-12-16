.PHONY: run setup clean help

run:
	@if [ ! -d ".venv" ]; then \
		echo "Error: Virtual environment not found. Run 'make setup' first."; \
		exit 1; \
	fi
	@echo "Starting Web Scraper API server..."
	@.venv/bin/uvicorn route:app --host 0.0.0.0 --port 8000 --reload

setup:
	@chmod +x setup.sh
	@./setup.sh

clean:
	@echo "Cleaning up"
	@rm -rf .venv
	@rm -rf __pycache__
	@rm -rf *.pyc
	@rm -rf .pytest_cache
	@echo "✓ Cleanup complete"
