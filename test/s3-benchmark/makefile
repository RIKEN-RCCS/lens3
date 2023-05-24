# makefile

all::

go::
	go build s3-benchmark.go

goinit::
	go mod init s3-benchmark

goget::
	go get github.com/aws/aws-sdk-go-v2/aws
	go get github.com/aws/aws-sdk-go-v2/config
	go get github.com/aws/aws-sdk-go-v2/credentials
	go get github.com/aws/aws-sdk-go-v2/service/s3

clean::
	rm -f s3-benchmark
