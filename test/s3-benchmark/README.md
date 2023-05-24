# Notes on s3-benchmark

This is a copy of s3-benchmark by wasabi-tech.  This part is
copyrighted by wasabi-tech and is licensed with LGPL.  The code is
much modified, including the change to "aws-sdk-go-v2" from "v1" in
the original.  The code is very much simplified to use s3.GetObject
and s3.PutObject, and drops monitoring of slow accesses (by http
status 503).  A line to create a bucket was removed, too, since Lens3
does not accept bucket operations.  Note that the original code used
an old signing algorithm (not "s3v4").

* Original README
  [README](README-ORIGINAL.md).
* Original source code on github.com
  [https://github.com/wasabi-tech/s3-benchmark.git]([https://github.com/wasabi-tech/s3-benchmark.git)
* Information on migration of aws-sdk-go:
  [https://aws.github.io/aws-sdk-go-v2/docs/migrating/](https://aws.github.io/aws-sdk-go-v2/docs/migrating/)

## Other Benchmarks

* https://github.com/minio/warp
