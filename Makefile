.PHONY: install install-dev install-ui test dashboard clean

install:
	uv pip install .

install-dev: install
	uv pip install '.[dev]'

install-ui: install
	uv pip install '.[ui]'

test:
	uv run pytest

dashboard:
	uv run streamlit run streamlit_app.py

clean:
	rm -rf build dist src/*.egg-info
