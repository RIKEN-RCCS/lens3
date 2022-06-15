# Stupid Tests

These (in "test/stupid") are very simple tests.  Note the tests leave
garbage files.  Run the tests in the "test/stupid" directory, because
some tests need sample files which are in "test/stupid".

The secret of S3 should be prepared in ".aws/*" in advance.  Also, the
environment variables "EP" and "BKT" are used as the target, "EP" as
an endpoint and "BKT" as a bucket name.  They can be specified by
creating a file and set-env "LENS3TEST" to the file name.

## copy-file.sh

[copy-file.sh](copy-file.sh) runs a very simple test using AWS S3 CLI.
It runs commands: __cp__, __ls__, __mv__, __rm__, __presign__.  It
generates a file of 32MB, and uploads and downloads it.  That file is
large enough to start a multipart upload (8MB is the default threshold
to use a multipart upload).

## set-website.sh

[set-website.sh](set-website.sh) runs the __website__ command.  It
will fail in Lens3.

## Info

For S3 CLI, refer to the links:
* [S3 CLI commands](https://docs.aws.amazon.com/cli/latest/reference/s3/index.html)
* [S3 CLI API commands](https://docs.aws.amazon.com/cli/latest/reference/s3api/index.html)
