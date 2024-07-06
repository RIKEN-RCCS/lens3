# Sporadic Test

## Description

Sporadic Test runs uploading/downloading in some interval,
indefinitely.  Those accesses to backend servers are set in timing
near starting/stopping of backends.  Triggering starting/stopping of
backends is the critical part in the working of Lens3.

Set "period" in "testconf.json" to match the value
"backend_awake_duration" in "mux-conf.json".  This period value is
randomized by some fluctuations.  "fluctuation" in "testconf.json" is
a percent of a plus/minus range, e.g., fluctuation=20 means ±20%.

It copies "size" data, by "count" times, with "threads" threads, for
each bucket in "stores".

## Buidling and Running A Test

Copy "testconf-example.json" as "testconf.json" and edit it
appropriately.

```
$ make get
$ make build
$ cp testconf-example.json testconf.json
$ vi testconf.json
$ ./sporadic-access
```
