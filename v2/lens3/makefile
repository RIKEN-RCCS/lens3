## makefile

#FLG=-v -x

all::
	go build $(FLG)

get::
	go get
	go mod tidy

get-u::
	go get -u
	go mod tidy

build-race::
	go build -race

install::
	go install .

clean::
	go clean -i -r -x -cache -testcache -modcache -fuzzcache

fmt::
	go fmt

vet::
	go vet

fix::
	go fix

mod::
	go mod graph
