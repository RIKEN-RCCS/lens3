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
	//"os"
	//"net"
	//"maps"
	//"net/http"
	//"net/http/httputil"
	//"net/url"
	//"regexp"
	//"slices"
	//"strings"
	"time"
	//"runtime"
	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/credentials"
	"github.com/aws/aws-sdk-go-v2/service/s3"
)

func probe_access_mux(m *multiplexer, ep string, secret *secret_record) error {
	var session = ""
	var muxurl = "http://" + ep
	var provider = credentials.NewStaticCredentialsProvider(
		secret.Access_key, secret.Secret_key, session)
	var options = s3.Options{
		BaseEndpoint: aws.String(muxurl),
		Credentials:  provider,
		Region:       "us-east-1",
		UsePathStyle: true,
	}
	var client *s3.Client = s3.New(options)
	var ctx = context.Background()
	var v, err1 = client.ListBuckets(ctx,
		&s3.ListBucketsInput{})
	if err1 != nil {
		logger.errf("Probing multiplexer failed: ep=(%s), err=(%v)",
			ep, err1)
		return err1
	}
	_ = v
	return nil
}

func list_buckets_in_backend(m *multiplexer, be *backend_record) []string {
	var session = ""
	var beurl = "http://" + be.Backend_ep
	var provider = credentials.NewStaticCredentialsProvider(
		be.Root_access, be.Root_secret, session)
	var options = s3.Options{
		BaseEndpoint: aws.String(beurl),
		Credentials:  provider,
		Region:       "us-east-1",
		UsePathStyle: true,
	}
	var client *s3.Client = s3.New(options)

	//var ctx = context.Background()
	var timeout = 1000 * time.Millisecond
	var ctx, cancel = context.WithTimeout(context.Background(), timeout)
	defer cancel()
	var v, err1 = client.ListBuckets(ctx,
		&s3.ListBucketsInput{})
	if err1 != nil {
		logger.errf("List buckets in backend failed: pool=(%s), err=(%v)",
			be.Pool, err1)
		return []string{}
	}
	var bkts []string
	for _, b := range v.Buckets {
		// (b : s3.types.Bucket).
		if b.Name != nil && *(b.Name) != "" {
			bkts = append(bkts, *(b.Name))
		}
	}
	return bkts
}

func make_bucket_in_backend(m *multiplexer, be *backend_record, bucket *bucket_record) bool {
	var session = ""
	var beurl = "http://" + be.Backend_ep
	var provider = credentials.NewStaticCredentialsProvider(
		be.Root_access, be.Root_secret, session)
	var options = s3.Options{
		BaseEndpoint: aws.String(beurl),
		Credentials:  provider,
		Region:       "us-east-1",
		UsePathStyle: true,
	}
	var client *s3.Client = s3.New(options)

	// var ctx = context.Background()
	var timeout = 1000 * time.Millisecond
	var ctx, cancel = context.WithTimeout(context.Background(), timeout)
	defer cancel()
	var v, err1 = client.CreateBucket(ctx,
		&s3.CreateBucketInput{
			Bucket: aws.String(bucket.Bucket),
		})
	if err1 != nil {
		logger.errf("Make a bucket in backend failed: bucket=(%s), err=(%v)",
			bucket.Bucket, err1)
		return false
	}
	fmt.Println("CreateBucket()=", v)
	return true
}
