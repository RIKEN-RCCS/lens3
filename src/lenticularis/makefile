# Copyright (c) 2022 RIKEN R-CCS
# SPDX-License-Identifier: BSD-2-Clause

PYCODESTYLE=pycodestyle --max-line-length=120

CC=gcc
CC=clang
CFLAGS+=-Wall -g -O2
CFLAGS+=-Wdeclaration-after-statement
CFLAGS+=-Wmissing-prototypes

#SUDO=/usr/bin/sudo
MINIO=/usr/local/bin/minio
LENTICULARIS=230

#CFLAGS+=-DSUDO='"$(SUDO)"'
CFLAGS+=-DMINIO='"$(MINIO)"'
CFLAGS+=-DLENTICULARIS=$(LENTICULARIS)

DENIED_USERS=0, 1, 2
CFLAGS+=-DDENIED_USERS="$(DENIED_USERS)"
ALLOWED_GROPUS=1001, 1002
CFLAGS+=-DALLOWED_GROPUS="$(ALLOWED_GROPUS)"

all::

suminio: suminio.o
	$(CC) -o $@ suminio.o

pycodestyle::
	-(pycodestyle --max-line-length=120 *.py) > pycodestyle-output.txt

pylint::
	-(pylint --rcfile=pylintrc *.py) > pylint-output.txt

pyright::
	-(pyright *.py) > pyright-output.txt
	@grep -E ".* errors?, .* warnings?, .* informations?" pyright-output.txt

typestubs::
	(pyright --createstub lenticularis.table)

tags::
	ctags *.py webui/scripts/*.js

clean::
	rm -rf suminio.o suminio
	rm -f tags

test::
	cd test && $(MAKE)
