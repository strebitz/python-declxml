check:
	flake8 --max-complexity 10 declxml.py

coverage:
	coverage run tests/run_tests.py

coverage-html:
	coverage run tests/run_tests.py
	coverage html
	rm -rf /tmp/htmlcov && mv htmlcov /tmp/
	open /tmp/htmlcov/index.html

coverage-report:
	coverage run tests/run_tests.py
	coverage report

test:
	pytest -v
