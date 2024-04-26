## makefile

#FLG=-v -x

all::
	go build $(FLG)

fmt::
	go fmt

vet::
	go vet

test::
	go test -run Test_misc

build-race::
	go build -race

install::
	go install .

clean::
	go clean -i -r -x

fix::
	go fix

get::
	go get -u golang.org/x/sys
	go get -u github.com/go-redis/redis/v8
	go get -u gopkg.in/yaml.v3
