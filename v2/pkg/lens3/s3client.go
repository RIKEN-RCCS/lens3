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
	"context"
	"fmt"
	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/credentials"
	"github.com/aws/aws-sdk-go-v2/service/s3"
	"github.com/aws/smithy-go"
	"math/rand/v2"
	"time"
)

// PROBE_ACCESS_MUX accesses a Mux from Registrar or other
// Multiplexers using a probe-key.  A probe-access starts a backend
// and amends its setting.  It chooses a Mux under which a backend is
// running, or randomly.  It uses "us-east-1" region, which can be
// arbitrary.
func probe_access_mux(t *keyval_table, pool string) error {
	var pooldata = get_pool(t, pool)
	if pooldata == nil {
		return fmt.Errorf("Pool not found: pool=(%s)", pool)
	}
	var secret = get_secret(t, pooldata.Probe_key)
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
	var region = "us-east-1"
	var options = s3.Options{
		BaseEndpoint: aws.String(muxurl),
		Credentials:  provider,
		Region:       region,
		UsePathStyle: true,
	}
	var client *s3.Client = s3.New(options)
	var ctx = context.Background()
	var v, err1 = client.ListBuckets(ctx,
		&s3.ListBucketsInput{})
	if err1 != nil {
		slogger.Error("Probing multiplexer failed", "ep", ep, "err", err1)
		return err1
	}
	_ = v
	return nil
}

func list_buckets_in_backend(w *manager, be *backend_record) ([]string, error) {
	var session = ""
	var beurl = "http://" + be.Backend_ep
	var provider = credentials.NewStaticCredentialsProvider(
		be.Root_access, be.Root_secret, session)
	var region = w.Backend_region
	var options = s3.Options{
		BaseEndpoint: aws.String(beurl),
		Credentials:  provider,
		Region:       region,
		UsePathStyle: true,
	}
	var client *s3.Client = s3.New(options)

	var timeout = (time.Duration(w.Backend_timeout_ms) * time.Millisecond)
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

func make_bucket_in_backend(w *manager, be *backend_record, bucket *bucket_record) bool {
	var session = ""
	var beurl = "http://" + be.Backend_ep
	var provider = credentials.NewStaticCredentialsProvider(
		be.Root_access, be.Root_secret, session)
	var region = w.Backend_region
	var options = s3.Options{
		BaseEndpoint: aws.String(beurl),
		Credentials:  provider,
		Region:       region,
		UsePathStyle: true,
	}
	var client *s3.Client = s3.New(options)

	var timeout = (time.Duration(w.Backend_timeout_ms) * time.Millisecond)
	var ctx, cancel = context.WithTimeout(context.Background(), timeout)
	defer cancel()
	var _, err1 = client.CreateBucket(ctx,
		&s3.CreateBucketInput{
			Bucket: aws.String(bucket.Bucket),
		})
	if err1 != nil {
		slogger.Error("Making a bucket in backend failed",
			"bucket", bucket.Bucket, "err", err1)
		return false
	}
	//fmt.Println("CreateBucket()=", v)
	return true
}

func heartbeat_backend(w *manager, be *backend_record) int {
	var session = ""
	var beurl = "http://" + be.Backend_ep
	var provider = credentials.NewStaticCredentialsProvider(
		be.Root_access, be.Root_secret, session)
	var region = w.Backend_region
	var options = s3.Options{
		BaseEndpoint: aws.String(beurl),
		Credentials:  provider,
		Region:       region,
		UsePathStyle: true,
	}
	var client *s3.Client = s3.New(options)

	var timeout = (time.Duration(w.Backend_timeout_ms) * time.Millisecond)
	var ctx, cancel = context.WithTimeout(context.Background(), timeout)
	defer cancel()
	var _, err1 = client.ListBuckets(ctx, &s3.ListBucketsInput{})
	if err1 != nil {
		var err2, ok1 = err1.(*smithy.OperationError)
		if ok1 {
			// The error is an canceled error, because it sets small 1~sec
			// timeout (err1.Err : *aws.RequestCanceledError).
			var err3, ok2 = (err2.Err).(*aws.RequestCanceledError)
			if ok2 {
				slogger.Warn("Heartbeat failed", "err", err3.Err)
			} else {
				slogger.Warn("Heartbeat failed", "err", err2.Err)
			}
		} else {
			slogger.Warn("Heartbeat failed", "err", err1)
		}
		return http_400_bad_request
	}

	//fmt.Printf("s3.Client.ListBuckets()=%#v\n", v)

	return http_200_OK
}
