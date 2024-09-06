## makefile

all::
	@echo '"make build" or "make install-boto3" or "make pyright"'

build::
	go build

fmt::
	go fmt

install-boto3::
	pip3 install --user -r requirements.txt

pyright::
	-(pyright *.py) > pyright-output.txt
	@grep -E ".* errors?, .* warnings?, .* informations?" pyright-output.txt

pyright-update::
	pip3 install --user -U pyright
