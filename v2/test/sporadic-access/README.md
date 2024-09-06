# Sporadic Access Test

## Description

[sporadic.go](sporadic.go) runs uploading/downloading files
sporadically and indefinitely.  It tests accesses at a timing near
starting/stopping of backend servers.  It is because triggering
starting/stopping of backends is a critical part.  The test should be
run for a long time, for example, a few days.

## Buidling

```
$ make get
$ make build
```

## Configuration

Copy "testconf-example.json" as "testconf.json" and edit it
appropriately.

- "__s3_ep__" is an S3 endpoint.
- "__size__", "__count__", and "__threads__" determines the copy
  operation in each iteration.  It copies "size" of data, with number
  of "threads", by "count" times.
- "__period__" and "__fluctuation__" determines a wait time between
  each iteration.  "period" is a wait time in second.  "fluctuation"
  is a randomize factor that is a percent in a plus/minus range.
  E.g., fluctuation=20 means ±20%.  "period" should be the same value
  as "backend_awake_duration" in Lens3 configuration
  ("mux-conf.json").
- "__stores__" is a list of buckets and their access keys.  Copy
  operation works on all "stores" in each iteration.

## Running

```
$ cp testconf-example.json testconf.json
$ vi testconf.json
$ ./sporadic-access
```
