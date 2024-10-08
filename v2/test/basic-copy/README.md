# Copy Files by AWS CLI

## copy-file.sh

[copy-file.sh](copy-file.sh) runs basic tests using AWS CLI.  It runs
commands: __cp__, __ls__, __mv__, and __rm__.

It first generates a file of 32MB randoms, and uploads and downloads
it.  The file size is large enough to start a multipart upload (8MB is
the default threshold to use a multipart upload).

## Install AWS CLI

It uses AWS Command Line Interface (AWS CLI).  For instructions of
installing AWS CLI, See
[Install AWS CLI](../README.md#install-aws-cli) in "v2/test/README.md"
file.

## Set Credentials for AWS CLI

First, prepare an S3 access key and a bucket in advance.

Second, store access/secret keys in the configuration file of AWS CLI
in "\~/.aws/credentials".  Optionally, set the S3 signature version in
the configuration file "\~/.aws/config".

"credentials" file looks like:
```
$ cat ~/.aws/credentials
[default]
aws_access_key_id = AlmlPM4qXMXKuyzCzbj6
aws_secret_access_key = OesFyGbSuO76HSs5gfmw69VPMEBtA1t9RxyfzTvg6LXeMsYV
```

"config" file looks like:
```
$ cat ~/.aws/config
[default]
s3 =
    signature_version = s3v4
```

## Run a Test

The shell variables "EP" and "BKT" specify the target: "EP" for an
endpoint, and "BKT" for a bucket.

It reads (sources by ".") a file "copy-file-conf.sh" if the file
exists.  Copy "copy-file-conf-example.sh" as "copy-file-conf.sh" and
edit it.  It may include variables "SIZ" for the file size, and "DBG"
for the options to AWS CLI.

Running "copy-file.sh" leaves garbage files in the current directory.

Note that it does not test the commands __presign__ and __website__.
__presign__ is useless because Lens3 does not understand a secret in
URL.  __website__ will fail in Lens3.
