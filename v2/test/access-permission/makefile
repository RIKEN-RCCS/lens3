## makefile

all::
	@echo make install-boto3 or make pyright

install-boto3::
	pip3 install --user -r requirements.txt

pyright::
	-(pyright *.py) > pyright-output.txt
	@grep -E ".* errors?, .* warnings?, .* informations?" pyright-output.txt

pyright-update::
	pip3 install --user -U pyright
