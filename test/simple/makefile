# makefile

all::
	@echo make installboto3 or make pyright

installboto3::
	pip3 install --user -r requirements.txt

PYFILES=apiclient.py basic_test.py

pyright::
	-(pyright $(PYFILES)) > pyright-output.txt
	@grep -E ".* errors?, .* warnings?, .* informations?" pyright-output.txt

pyright-update::
	pip3 install --user -U pyright
