# Registrar Access Test

## Description

[test_registrar.py](test_registrar.py) checks accesses to Registrar.
It makes some buckets and keys.  It uses "boto3" library.

The "client.json" file should contain access information to Lens3.  It
can be prepared by copying an example file "client-example.json".  See
[Client Setting](../README.md#client-setting) in "v2/test/README.md" file.

It requires Python library "boto3".  It should be installed, maybe, by
running "make install-boto3".  See
[Python Setting](../README.md#python-setting) in "v2/test/README.md" file.
