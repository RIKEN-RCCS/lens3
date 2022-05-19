# Copyright (c) 2022 RIKEN R-CCS
# SPDX-License-Identifier: BSD-2-Clause

PYCODESTYLE=pycodestyle --max-line-length=120

all:: suminio pep8 test

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

suminio: suminio.o
	$(CC) -o $@ suminio.o

clean:
	rm -rf suminio.o suminio
	rm -f tags

pep8::
	-$(PYCODESTYLE) \
	adm.py \
	admin.py \
	api.py \
	controller.py \
	dbase.py \
	lockdb.py \
	manager.py \
	mc.py \
	multiplexer.py \
	mux.py \
	pooladm.py \
	poolutil.py \
	readconf.py \
	scheduler.py \
	start_service.py \
	table.py \
	utility.py

tags::
	ctags *.py webui/scripts/*.js

test::
	cd test && $(MAKE)
