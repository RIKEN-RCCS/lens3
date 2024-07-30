/* AWS S3 Client for a Backend. */

// Copyright 2022-2024 RIKEN R-CCS
// SPDX-License-Identifier: BSD-2-Clause

package lens3

// This defines a few S3 operations to a backend server --
// list-buckets and make-bucket.

// S3 operations return "aws/smithy/OperationError", but it wraps
// other errors in a deep nest.  Extraction of an S3 operation error
// from it is done by unwrap_operation_error().
//
// See https://aws.github.io/aws-sdk-go-v2/docs/handling-errors/

// MEMO: The "aws/smithy/OperationError" wraps errors in a deep nest
// such as "aws/retry/MaxAttemptsError", "aws/RequestCanceledError".
// ResponseError is defined in several packages like
// "service/internal/s3shared/ResponseError".
// "aws/transport/http/ResponseError"
// "aws/smithy-go/transport/http/ResponseError".
//
// See https://pkg.go.dev/github.com/aws/smithy-go

// MEMO: S3 clients retry on HTTP status 50x but 501.
//
// See https://pkg.go.dev/github.com/aws/aws-sdk-go-v2/aws/retry

import (
	"context"
	"errors"
	"github.com/aws/aws-sdk-go-v2/aws"
	awshttp "github.com/aws/aws-sdk-go-v2/aws/transport/http"
	"github.com/aws/aws-sdk-go-v2/credentials"
	"github.com/aws/aws-sdk-go-v2/service/s3"
	"github.com/aws/smithy-go"
	"github.com/aws/smithy-go/logging"
	"log/slog"
	"time"
)

const s3_region_default = "us-east-1"

func list_buckets_in_backend(w *manager, be *backend_record) ([]string, error) {
	var pool = be.Pool

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
		var err2 = unwrap_operation_error(err1)
		slogger.Error("Listing buckets in backend failed",
			"pool", pool, "err", err2)
		return nil, err2
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
	var pool = be.Pool
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
		var err2 = unwrap_operation_error(err1)
		slogger.Error("Making bucket in backend failed",
			"pool", pool, "bucket", name, "err", err2)
		return err2
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

// UNWRAP_OPERATION_ERROR unwraps nested errors to find out an error
// from an S3 operation.  It checks smithy/APIError or
// awshttp/ResponseError.  A returned error is, for example,
// types/BucketAlreadyOwnedByYou, defined in aws/service/s3/types.
// Note that APIError is more specific than ResponseError as
// ResponseError includes smithy/CanceledError, but APIError does not.
func unwrap_operation_error(e1 error) error {
	var e2 smithy.APIError
	if errors.As(e1, &e2) {
		//fmt.Printf("*** APIError=(%#v)\n", e2)
		return e2
	}
	var e3 *awshttp.ResponseError
	if errors.As(e1, &e3) {
		//var rspn = e3.Response
		//var body, _ = io.ReadAll(rspn.Body)
		return e3.Unwrap()
	}
	return e1
}
