all:

install::
	pip3 install --user -r requirements.txt

pyright::
	(cd src; pyright lenticularis/*.py) > /tmp/pyright-output.txt

typestub::
	(cd src; pyright --createstub lenticularis.scheduler)

ARCHIVE=/tmp/archive-$$(date +%Y%m%d).zip
FORMAT=zip

archive::
	git archive HEAD --format=$(FORMAT) -o $(ARCHIVE)
