/* AWS S3 Client for a Backend. */

// Copyright 2022-2024 RIKEN R-CCS
// SPDX-License-Identifier: BSD-2-Clause

package lens3

// MEMO: Errors from S3 clients are wrapped or embedded in
// "aws/smithy/OperationError".  The "OperationError" consists of
// {ServiceID, OperationName, Err}.  It wraps errors such as
// "aws/retry/MaxAttemptsError" and "aws/RequestCanceledError".
// "aws/retry/MaxAttemptsError" further wraps
// "service/internal/s3shared/ResponseError".  It further wraps
// "aws/transport/http/ResponseError".  It further wraps
// "aws/smithy-go/transport/http/ResponseError".  (Note that "awshttp"
// is an alias of "aws/transport/http").
//
// See https://pkg.go.dev/github.com/aws/smithy-go

// HTTP retry is configurable.  S3 clients retry on HTTP status 50x
// but 501.
//
// See https://pkg.go.dev/github.com/aws/aws-sdk-go-v2/aws/retry

import (
	"context"
	"errors"
	"fmt"
	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/aws/retry"
	"github.com/aws/aws-sdk-go-v2/credentials"
	"github.com/aws/aws-sdk-go-v2/service/s3"
	"github.com/aws/smithy-go"
	"github.com/aws/smithy-go/logging"
	"log/slog"
	"math/rand/v2"
	"time"
)

const s3_region_default = "us-east-1"

// PROBE_ACCESS_MUX accesses a Multiplexer using a probe-key from
// Registrar.  A probe-access tries to make buckets absent in the
// backend.  It uses list buckets but it is ignored by a Multiplexer.
// Region and timeout used is fairly arbitrary.
func probe_access_mux(t *keyval_table, pool string) error {
	// Dummy manager just to pass region and timeout
	var w = &manager{}
	w.Backend_region = s3_region_default
	w.Backend_timeout_ms = time_in_ms(1000)

	var pooldata = get_pool(t, pool)
	if pooldata == nil {
		var err1 = fmt.Errorf("Pool not found: pool=%q", pool)
		slogger.Error("Probe-access fails", "pool", pool, "err", err1)
		panic(nil)
	}
	var secret = get_secret(t, pooldata.Probe_key)
	if secret == nil {
		var err2 = fmt.Errorf("Probe-key not found: pool=%q", pool)
		slogger.Error("Probe-access fails", "pool", pool, "err", err2)
		panic(nil)
	}

	var ep string
	var be1 = get_backend(t, pool)
	if be1 != nil {
		ep = be1.Mux_ep
	} else {
		var eps []*mux_record = list_mux_eps(t)
		if len(eps) == 0 {
			var err3 = fmt.Errorf("No Multiplexers")
			slogger.Error("Probe-access fails", "pool", pool, "err", err3)
			return err3
		}
		var i = rand.IntN(len(eps))
		ep = eps[i].Mux_ep
	}

	var session = ""
	var url1 = ("http://" + ep)
	var provider = credentials.NewStaticCredentialsProvider(
		secret.Access_key, secret.Secret_key, session)
	var region = w.Backend_region
	var options = s3.Options{
		BaseEndpoint:     aws.String(url1),
		Credentials:      provider,
		Region:           region,
		UsePathStyle:     true,
		Logger:           make_aws_logger(slogger),
		RetryMaxAttempts: 1,
	}
	var client *s3.Client = s3.New(options)

	var timeout = (w.Backend_timeout_ms).time_duration()
	var ctx, cancel = context.WithTimeout(context.Background(), timeout)
	defer cancel()
	var _, err4 = client.ListBuckets(ctx, &s3.ListBucketsInput{})
	if err4 != nil {
		slogger.Error("Probe-access fails", "pool", pool,
			"ep", ep, "err", err4)
		return err4
	}
	return nil
}

func list_buckets_in_backend(w *manager, be *backend_record) ([]string, error) {
	var session = ""
	var url1 = ("http://" + be.Backend_ep)
	var provider = credentials.NewStaticCredentialsProvider(
		be.Root_access, be.Root_secret, session)
	var region = w.Backend_region
	var options = s3.Options{
		BaseEndpoint: aws.String(url1),
		Credentials:  provider,
		Region:       region,
		UsePathStyle: true,
		Logger:       make_aws_logger(slogger),
	}
	var client *s3.Client = s3.New(options)

	var timeout = (w.Backend_timeout_ms).time_duration()
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

func make_bucket_in_backend(w *manager, be *backend_record, bucket *bucket_record) error {
	var name = bucket.Bucket

	var session = ""
	var url1 = ("http://" + be.Backend_ep)
	var provider = credentials.NewStaticCredentialsProvider(
		be.Root_access, be.Root_secret, session)
	var region = w.Backend_region
	var options = s3.Options{
		BaseEndpoint: aws.String(url1),
		Credentials:  provider,
		Region:       region,
		UsePathStyle: true,
		Logger:       make_aws_logger(slogger),
	}
	var client *s3.Client = s3.New(options)

	var timeout = (w.Backend_timeout_ms).time_duration()
	var ctx, cancel = context.WithTimeout(context.Background(), timeout)
	defer cancel()
	var _, err1 = client.CreateBucket(ctx,
		&s3.CreateBucketInput{
			Bucket: aws.String(name),
		})
	if err1 != nil {
		slogger.Error("Making a bucket in backend failed",
			"bucket", name, "err", err1)
		return err1
	}
	//fmt.Println("CreateBucket()=", v)
	return nil
}

// HEARTBEAT_BACKEND calls list buckets in the backend.  An error is
// an canceled error, because it sets small timeout 1~sec (thus,
// err1.Err : *aws/RequestCanceledError).
func heartbeat_backend(w *manager, be *backend_record) int {
	var session = ""
	var url1 = ("http://" + be.Backend_ep)
	var provider = credentials.NewStaticCredentialsProvider(
		be.Root_access, be.Root_secret, session)
	var region = w.Backend_region
	var options = s3.Options{
		BaseEndpoint: aws.String(url1),
		Credentials:  provider,
		Region:       region,
		UsePathStyle: true,
		Logger:       make_aws_logger(slogger),
	}
	var client *s3.Client = s3.New(options)

	var timeout = (w.Backend_timeout_ms).time_duration()
	var ctx, cancel = context.WithTimeout(context.Background(), timeout)
	defer cancel()
	var _, err1 = client.ListBuckets(ctx, &s3.ListBucketsInput{})
	if err1 != nil {
		var err2, ok1 = err1.(*smithy.OperationError)
		if ok1 {
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

func unwrap_operation_error(e1 error) error {
	if false {
		switch e2 := e1.(type) {
		case *smithy.OperationError:
			// {ServiceID, OperationName, Err}.
			switch e3 := (e2.Err).(type) {
			case *retry.MaxAttemptsError:
				// {Attempt, Err}.
				return e3.Err
			case *aws.RequestCanceledError:
				// {Err}.
				return e3
			default:
				return e2.Err
			}
		default:
			return e1
		}
	}

	var ex = e1
	for {
		var e2 = errors.Unwrap(ex)
		fmt.Printf("*** Unwrap(%#v)=%#v\n", ex, e2)
		if e2 == nil {
			return ex
		}
		ex = e2
	}
}

type slog_writer struct {
	h slog.Handler
}

func make_aws_logger(slog *slog.Logger) logging.Logger {
	var h = slog.Handler()
	var awslogger = logging.NewStandardLogger(&slog_writer{h})
	return awslogger
}

// WRITE writes to slogger.  It returns a wrong length of a message.
func (w *slog_writer) Write(buf []byte) (int, error) {
	var level = slog.LevelWarn
	if !w.h.Enabled(context.Background(), level) {
		return 0, nil
	}
	var s = string(buf)
	var r = slog.NewRecord(time.Now(), level, "S3 client error", 0)
	r.Add("err", s)
	var err = w.h.Handle(context.Background(), r)
	return len(s), err
}
