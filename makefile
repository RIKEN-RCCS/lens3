all:

install::
	pip3 install --user -r requirements.txt

pyright::
	(cd src; pyright lenticularis/*.py) > pyright-log.txt

ARCHIVE=/tmp/archive-$$(date +%Y%m%d).zip
FORMAT=zip

archive::
	git archive HEAD --format=$(FORMAT) -o $(ARCHIVE)
