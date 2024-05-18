/* AWS S3 Client for a Backend. */

// Copyright 2022-2024 RIKEN R-CCS
// SPDX-License-Identifier: BSD-2-Clause

package lens3

import (
	"fmt"
	//"flag"
	"context"
	//"io"
	//"log"
	"os"
	//"net"
	//"maps"
	//"net/http"
	//"net/http/httputil"
	//"net/url"
	//"regexp"
	//"slices"
	//"strings"
	//"time"
	//"runtime"
	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/credentials"
	"github.com/aws/aws-sdk-go-v2/service/s3"
)

func make_bucket_in_backend(z *registrar, pool string, makebucket *make_bucket_request) bool {
	var provider = credentials.NewStaticCredentialsProvider(
		"key",
		"secret",
		"session")
	var options = s3.Options{
		BaseEndpoint: aws.String("http://localhost:9001/"),
		Credentials:  provider,
		Region:       "us-east-1",
		UsePathStyle: true,
	}
	var client *s3.Client = s3.New(options)

	var ctx = context.Background()
	var bo, err1 = client.CreateBucket(ctx,
		&s3.CreateBucketInput{
			Bucket: aws.String("bucket"),
		})
	_ = bo

	if err1 != nil {
		fmt.Printf("Unable to create bucket %q, %v", "bucket", err1)
		os.Exit(1)
	}

	return true
}
