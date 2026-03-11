## makefile

#FLG=-v -x

build::
	go build ./cmd/lenticularis-mux
	go build ./cmd/lenticularis-admin

get::
	cd lens3; go get
	cd cmd/lenticularis-mux; go get
	cd cmd/lenticularis-admin; go get
	go mod tidy
