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
	go clean -i -r -x -cache -testcache -modcache -fuzzcache

fix::
	go fix

get::
	go get github.com/aws/aws-sdk-go-v2/aws
	go get github.com/aws/aws-sdk-go-v2/credentials
	go get github.com/aws/aws-sdk-go-v2/service/s3
	go get github.com/aws/smithy-go
	go get github.com/eclipse/paho.golang/autopaho
	go get github.com/eclipse/paho.golang/paho
	go get github.com/go-redis/redis/v8
	go get golang.org/x/sys
	go mod tidy

get-u::
	go get -u github.com/aws/aws-sdk-go-v2/aws
	go get -u github.com/aws/aws-sdk-go-v2/credentials
	go get -u github.com/aws/aws-sdk-go-v2/service/s3
	go get -u github.com/aws/smithy-go
	go get -u github.com/eclipse/paho.golang/autopaho
	go get -u github.com/eclipse/paho.golang/paho
	go get -u github.com/go-redis/redis/v8
	go get -u golang.org/x/sys
	go mod tidy

mod::
	go mod graph
