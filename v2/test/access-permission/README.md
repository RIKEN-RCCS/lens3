# Access Permission Test

## test_permission.py

[test_permission.py](test_permission.py) runs S3 access test.  It uses
"boto3" library.  It tests various combinations of key policies and
bucket policies, along with key's expiration states.

IT SHOULD CHECK METHODS: HEAD,GET,PUT,POST,DELETE.

HEAD: {HeadBucket, HeadObject, ...}
GET: {GetObject, ...}
PUT: {PutObject, ...}
POST: {DeleteObjects, RestoreObject, SelectObjectContent,...}
DELETE: {DeleteBucket, DeleteObject, ...}
