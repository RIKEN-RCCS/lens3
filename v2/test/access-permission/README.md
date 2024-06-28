# Access Permission Test

test_permission.py

## Description

[test_permission.py](test_permission.py) checks permission of
accesses.  It tests various combinations of key policies and bucket
policies, along with key's expiration states.  It uses "boto3"
library.

The "client.json" file should contain access information to Lens3.  It
should be prepared by copying an example file "client-example.json".
See "../lib/lens3_client.py" for setting.

It checks the HTTP methods: {HEAD, GET, PUT, POST, DELETE}.  The below
lists the methods used in S3 operations:

  HEAD: {HeadBucket, HeadObject, ...}
  GET: {GetObject, ...}
  PUT: {PutObject, ...}
  POST: {DeleteObjects, RestoreObject, SelectObjectContent,...}
  DELETE: {DeleteBucket, DeleteObject, ...}

## Running A Test

```
$ make install-boto3
$ python3 test_permission.py
```
