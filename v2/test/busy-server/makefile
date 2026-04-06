## makefile

all::
	@echo '"make pyright"'

pyright::
	-(pyright *.py) > pyright-output.txt
	@grep -E ".* errors?, .* warnings?, .* informations?" pyright-output.txt

pyright-update::
	pip3 install --user -U pyright
