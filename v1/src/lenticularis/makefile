# Copyright (c) 2022 RIKEN R-CCS
# SPDX-License-Identifier: BSD-2-Clause

PYCODESTYLE=pycodestyle --max-line-length=120

all::

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
	pyright --createstub lenticularis.dbase
	pyright --createstub lenticularis.readconf
	pyright --createstub lenticularis.utility

tags::
	ctags *.py webui/scripts/*.js

clean::
	rm -f tags

test::
	cd test && $(MAKE)
