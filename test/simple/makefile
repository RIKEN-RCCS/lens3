# makefile

all::

restore::
	echo "DO NOT FORGET 'sudo usermod -a -G lens3 $$(whoami)'"
	./dump-restore-test.sh

install:
	pip3 -qq install -r requirements.txt --user

tags::
	ctags *.py

clean::
	rm tags

PYFILES=lens3client.py apitest.py s3test.py

pyright::
	-(pyright $(PYFILES)) > pyright-output.txt
	@grep -E ".* errors?, .* warnings?, .* informations?" pyright-output.txt

pyright-update::
	pip3 install --user -U pyright
