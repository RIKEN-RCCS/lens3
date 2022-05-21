## makefile

all::
	@echo "USAGE: make install"

install::
	pip3 install --user -r requirements.txt

pycodestyle::
	-(cd src/lenticularis ; pycodestyle --max-line-length=120 *.py) > pycodestyle-output.txt

pylint::
	-(cd src/lenticularis ; pylint --rcfile=pylintrc *.py) > pylint-output.txt

pyright::
	-(cd src ; pyright lenticularis/*.py) > pyright-output.txt
	@grep -E ".* errors?, .* warnings?, .* informations?" pyright-output.txt

typestubs::
	(cd src ; pyright --createstub lenticularis.table)
