/* AWS S3 Client for a Backend. */

// Copyright 2022-2024 RIKEN R-CCS
// SPDX-License-Identifier: BSD-2-Clause

package lens3

// MEMO: The errors from clients are wrapped with
// "aws.smithy.OperationError".  The "OperationError" consists of
// {ServiceID, OperationName, Err}.  It wraps errors such as
// "aws.retry.MaxAttemptsError", "aws.RequestCanceledError"...
// "aws.retry.MaxAttemptsError" further wraps
// "service.internal.s3shared.ResponseError" in
// "github.com/aws/aws-sdk-go-v2".  It embeds
// "aws.transport.http.ResponseError" (Note "awshttp" is an alias).
// It embeds "aws.smithy-go.transport.http.ResponseError".
//
// See https://pkg.go.dev/github.com/aws/smithy-go

import (
	"fmt"
	//"flag"
	//"errors"
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
	"math/rand/v2"
	"time"
	//"github.com/aws/smithy-go"
	//"runtime"
	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/credentials"
	"github.com/aws/aws-sdk-go-v2/service/s3"
)

// PROBE_ACCESS_MUX accesses a Mux with a probe-key.  It chooses one
// under which a backend is running, or randomly.
func probe_access_mux(t *keyval_table, pool string) error {
	var prop = get_pool(t, pool)
	if prop == nil {
		return fmt.Errorf("Pool not found: pool=(%s)", pool)
	}
	var secret = get_secret(t, prop.Probe_key)
	if secret == nil {
		return fmt.Errorf("Probe-key not found: pool=(%s)", pool)
	}

	var ep string
	var be1 = get_backend(t, pool)
	if be1 != nil {
		ep = be1.Mux_ep
	} else {
		var eps []*mux_record = list_mux_eps(t)
		if len(eps) == 0 {
			return fmt.Errorf("No Mux running")
		}
		var i = rand.IntN(len(eps))
		ep = eps[i].Mux_ep
	}

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

func list_buckets_in_backend(m *multiplexer, be *backend_record) ([]string, error) {
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
	var timeout = 10000 * time.Millisecond
	var ctx, cancel = context.WithTimeout(context.Background(), timeout)
	defer cancel()
	var v, err1 = client.ListBuckets(ctx, &s3.ListBucketsInput{})
	if err1 != nil {
		fmt.Printf("client.ListBuckets() err=%T %#v\n", err1, err1)
		return nil, err1
	}
	var bkts []string
	for _, b := range v.Buckets {
		// (b : s3.types.Bucket).
		if b.Name != nil && *(b.Name) != "" {
			bkts = append(bkts, *(b.Name))
		}
	}
	return bkts, nil
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
