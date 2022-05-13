all:

install::
	pip3 install --user -r requirements.txt

pyright::
	(cd src; pyright lenticularis/*.py) > pyright-output.txt

typestubs::
	(cd src; pyright --createstub lenticularis.scheduler)

pylint::
	(cd src/lenticularis; pylint *.py) > pylint-output.txt
