# Access Permission Test

## Description

[test_permission.py](test_permission.py) checks permission of
accesses.  It tests various combinations of key policies and bucket
policies, along with key's expiration states.  It uses "boto3"
library.

The "client.json" file should contain access information to Lens3.  It
should be prepared by copying an example file "client-example.json".
See "../lib/lens3_client.py" for setting it.

* __"s3_ep"__: an endpoint of S3
* __"reg_ep"__: an endpoint of Lens3 Registrar
* __"gid"__: a unix group id used to create a pool
* __"home"__: a working directory under with a pool is created
* __"cred"__: a secret to access Lens3 Registrar

Running a test first creates a pool named "00XXXXXX" in the directory
in the home specified "client.json", and then creates some buckets
named "lenticularis-oddity-XXXXXX" in that pool.

It checks the HTTP methods: {HEAD, GET, PUT, POST, DELETE}.  The below
lists the methods with some S3 operations that uses them.

* HEAD: {HeadBucket, HeadObject, ...}
* GET: {GetObject, ...}
* PUT: {PutObject, ...}
* POST: {DeleteObjects, RestoreObject, SelectObjectContent,...}
* DELETE: {DeleteBucket, DeleteObject, ...}

## Running A Test

```
$ make install-boto3
$ python3 test_permission.py
```
