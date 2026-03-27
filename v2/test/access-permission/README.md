# Access Permission Test

[test_permission.py](test_permission.py) checks permission of
accesses.  It tests various combinations of key policies and bucket
policies, along with key's expiration states.  It uses "boto3"
library.

## Running the Test

It needs Python library "boto3".  It should be installed, maybe, by
running "make install-boto3".  See
[Python Setting](../README.md#python-setting) in "v2/test/README.md"
file.

The "client.json" file contains the test setting.  It is prepared by
copying an example file "client-example.json".  See
[Client Setting](../README.md#client-setting) in "v2/test/README.md"
file.

Running a test needs two directories for pools, specified by "pool"
and "pool2" in "client.json".  It creates some buckets named
"lenticularis-oddity-XXXXXX" in the pool named by "pool".  Another
pool named by "pool2" is used create unusable keys.  The two
directories should be created beforehand.

```
python3 test_permission.py
```

## What is Tested

The test checks the HTTP methods: {HEAD, GET, PUT, POST, DELETE}.  The
below lists the methods with some S3 operations that uses them.

* HEAD: {HeadBucket, HeadObject, ...}
* GET: {GetObject, ...}
* PUT: {PutObject, ...}
* POST: {DeleteObjects, ...}
* DELETE: {DeleteBucket, DeleteObject, ...}
