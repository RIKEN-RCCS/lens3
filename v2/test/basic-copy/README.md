# Copy Files by AWS CLI

## copy-file.sh

[copy-file.sh](copy-file.sh) runs basic tests using AWS CLI.  It runs
commands: __cp__, __ls__, __mv__, and __rm__.

It first generates a file of 32MB randoms, and uploads and downloads
it.  The file size is large enough to start a multipart upload (8MB is
the default threshold to use a multipart upload).

First, prepare S3 access/secret keys and a bucket in advance.  The
keys should be stored in the configuration file for AWS CLI, thus in
"~/.aws/credentials".  And optionally, the S3 signature version should
be set in the configuration file "~/.aws/config".

"~/.aws/credentials" looks like:

```
[default]
aws_access_key_id = AlmlPM4qXMXKuyzCzbj6
aws_secret_access_key = OesFyGbSuO76HSs5gfmw69VPMEBtA1t9RxyfzTvg6LXeMsYV
```

and "~/.aws/config" looks like:

```
[default]
s3 =
    signature_version = s3v4
```

The shell variables "EP" and "BKT" specify the target -- "EP" for an
endpoint and "BKT" for a bucket.  It reads (sources by ".") a file
"copy-file-conf.sh" if the file exists.  Copy
"copy-file-conf-example.sh" as "copy-file-conf.sh" and edit it.  It
may include variables "SIZ" for the file size, and "DBG" for the
options to AWS CLI.

Running "copy-file.sh" leaves garbage files in the current directory.

Note that it does not test the commands __presign__ and __website__.
__presign__ is useless because Lens3 does not understand a secret in
URL.  __website__ will fail in Lens3.

## Info

For S3 CLI, refer to the links:
* [S3 CLI commands](https://awscli.amazonaws.com/v2/documentation/api/latest/reference/s3/index.html)
* [S3 CLI API commands](https://awscli.amazonaws.com/v2/documentation/api/latest/reference/s3api/index.html)
