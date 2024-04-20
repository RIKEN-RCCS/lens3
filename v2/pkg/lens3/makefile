## makefile

#FLG=-v -x

all::
	go build $(FLG)

fmt::
	go fmt

vet::
	go vet

test::
	go test -run Test_manager

install::
	go install .

get::
	go get github.com/go-redis/redis/v8
	go get gopkg.in/yaml.v3
