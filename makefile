all: archive

install::
	pip3 -qq install -r requirements.txt --user

ARCHIVE=/tmp/archive-$$(date +%Y%m%d).zip
FORMAT=zip

archive::
	git archive HEAD --format=$(FORMAT) -o $(ARCHIVE)
