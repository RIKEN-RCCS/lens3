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
	-(pycodestyle --config=pycodestyle *.py) > pycodestyle-output.txt

pylint::
	-(pylint --rcfile=pylintrc *.py) > pylint-output.txt

pyright::
	-(pyright *.py) > pyright-output.txt
	@grep -E ".* errors?, .* warnings?, .* informations?" pyright-output.txt

pyright-update::
	pip3 install --user -U pyright

typestubs::
	pyright --createstub redis
	pyright --createstub starlette
	pyright --createstub fastapi
	pyright --createstub fastapi.requests
	pyright --createstub fastapi.staticfiles
	pyright --createstub fastapi.responses
	pyright --createstub fastapi_csrf_protect
	pyright --createstub fastapi_csrf_protect.exceptions

typestubs0::
	pyright --createstub lenticularis
	pyright --createstub lenticularis.api
	pyright --createstub lenticularis.readconf
	pyright --createstub lenticularis.utility

tags::
	ctags *.py webui/scripts/*.js

clean::
	rm -rf suminio.o suminio
	rm -f tags

test::
	cd test && $(MAKE)
