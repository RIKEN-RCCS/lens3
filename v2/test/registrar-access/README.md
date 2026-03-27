# Registrar Access Test

[test_registrar.py](test_registrar.py) checks accesses to Registrar.
It accesses Registrar (mimicing Web-UI), and makes a couple of buckets
and keys.  It uses "boto3" library.

## Running the Test

It needs Python library "boto3".  It should be installed, maybe, by
running "make install-boto3".  See
[Python Setting](../README.md#python-setting) in "v2/test/README.md"
file.

The "client.json" file contains the test setting.  It is prepared by
copying an example file "client-example.json".  See
[Client Setting](../README.md#client-setting) in "v2/test/README.md"
file.

The test accesses Registrar, and thus, it needs the credential to
Registrar in "client.json".  For example, the "auth" entry is "basic"
and the "cred" entry is a pair "[user-id, password]".

Run the test with:

```
python3 test_registrar.py
```

The functions to access Lens3 can be found in "../lib/lens3_client.py"
