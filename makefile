## makefile

all::
	@echo "USAGE: make install"

install::
	pip3 install --user -r requirements.txt

pycodestyle::
	cd src/lenticularis ; make pycodestyle

pylint::
	cd src/lenticularis ; make pylint

pyright::
	cd src/lenticularis ; make pyright
