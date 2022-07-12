// s3-benchmark.go
// Copyright (c) 2017 Wasabi Technology, Inc.

package main

import (
	"bytes"
	"code.cloudfoundry.org/bytefmt"
	"context"
	"crypto/md5"
	"encoding/base64"
	"flag"
	"fmt"
	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/config"
	"github.com/aws/aws-sdk-go-v2/credentials"
	"github.com/aws/aws-sdk-go-v2/service/s3"
	"io"
	"io/ioutil"
	"log"
	"math/rand"
	//"net"
	"net/http"
	"os"
	"strings"
	"sync"
	"sync/atomic"
	"time"
)

// Global variables
var access_key, secret_key, url_host, bucket, region string
var duration_secs, threads, loops int
var object_size uint64
var object_data []byte
var object_data_md5 string
var running_threads, upload_count, download_count, delete_count, upload_slowdown_count, download_slowdown_count, delete_slowdown_count int32
var endtime, upload_finish, download_finish, delete_finish time.Time

func logit(msg string) {
	fmt.Println(msg)
	logfile, _ := os.OpenFile("benchmark.log", os.O_WRONLY|os.O_CREATE|os.O_APPEND, 0666)
	if logfile != nil {
		logfile.WriteString(time.Now().Format(http.TimeFormat) + ": " + msg + "\n")
		logfile.Close()
	}
}

func getS3Client() *s3.Client {
	// Build our config
	customresolver := aws.EndpointResolverWithOptionsFunc(
		func(service, region string, options ...interface{}) (aws.Endpoint, error) {
			return aws.Endpoint{
				//PartitionID:   "aws",
				URL:           url_host,
				SigningRegion: region,
			}, nil
		})
	cfg, err := config.LoadDefaultConfig(context.TODO(),
		config.WithEndpointResolverWithOptions(customresolver),
		config.WithCredentialsProvider(
			credentials.NewStaticCredentialsProvider(access_key, secret_key,
				"")))
	if err != nil {
		log.Fatalf("FATAL: Unable to create new client.")
	}

	//fmt.Printf("CFG=%v\n", cfg)
	client := s3.NewFromConfig(cfg)
	if client == nil {
		log.Fatalf("FATAL: Unable to create new client.")
	}
	// Return success
	return client
}

func createBucket(ignore_errors bool) {
	// Get a client
	client := getS3Client()
	// Create our bucket (may already exist without error)
	in := &s3.CreateBucketInput{Bucket: aws.String(bucket)}
	if _, err := client.CreateBucket(context.TODO(), in); err != nil {
		if ignore_errors {
			log.Printf("WARNING: createBucket %s error, ignoring %v", bucket, err)
		} else {
			log.Fatalf("FATAL: Unable to create bucket %s (is your access and secret correct?): %v", bucket, err)
		}
	}
}

func deleteAllObjects() {
	// Get a client
	client := getS3Client()
	// Use multiple routines to do the actual delete
	var doneDeletes sync.WaitGroup
	// Loop deleting our versions reading as big a list as we can
	var keyMarker, versionId *string
	var err error
	for loop := 1; ; loop++ {
		// Delete all the existing objects and versions in the bucket
		in := &s3.ListObjectVersionsInput{Bucket: aws.String(bucket), KeyMarker: keyMarker, VersionIdMarker: versionId, MaxKeys: 1000}
		if listVersions, listErr := client.ListObjectVersions(context.TODO(), in); listErr == nil {
			/*
				delete := &s3.Delete{Quiet: aws.Bool(true)}
				for _, version := range listVersions.Versions {
					delete.Objects = append(delete.Objects, &s3.ObjectIdentifier{Key: version.Key, VersionId: version.VersionId})
				}
				for _, marker := range listVersions.DeleteMarkers {
					delete.Objects = append(delete.Objects, &s3.ObjectIdentifier{Key: marker.Key, VersionId: marker.VersionId})
				}
				if len(delete.Objects) > 0 {
					// Start a delete routine
					doDelete := func(bucket string, delete *s3.Delete) {
						if _, e := client.DeleteObjects(context.TODO(), &s3.DeleteObjectsInput{Bucket: aws.String(bucket), Delete: delete}); e != nil {
							err = fmt.Errorf("DeleteObjects unexpected failure: %s", e.Error())
						}
						doneDeletes.Done()
					}
					doneDeletes.Add(1)
					go doDelete(bucket, delete)
				}
				// Advance to next versions
				if listVersions.IsTruncated == nil || !*listVersions.IsTruncated {
					break
				}
			*/
			keyMarker = listVersions.NextKeyMarker
			versionId = listVersions.NextVersionIdMarker
		} else {
			// The bucket may not exist, just ignore in that case
			if strings.HasPrefix(listErr.Error(), "NoSuchBucket") {
				return
			}
			err = fmt.Errorf("ListObjectVersions unexpected failure: %v", listErr)
			break
		}
	}
	// Wait for deletes to finish
	doneDeletes.Wait()
	// If error, it is fatal
	if err != nil {
		log.Fatalf("FATAL: Unable to delete objects from bucket: %v", err)
	}
}

func runUpload(thread_num int) {
	client := getS3Client()
	for time.Now().Before(endtime) {
		n := atomic.AddInt32(&upload_count, 1)
		objectname := fmt.Sprintf("Object-%d", (n - 1))
		file := bytes.NewReader(object_data)
		input := &s3.PutObjectInput{
			Bucket: aws.String(bucket),
			Key:    aws.String(objectname),
			Body:   file,
		}
		_, err := client.PutObject(context.TODO(),
			input,
			func(u *s3.Options) {
				u.UsePathStyle = true
			})
		if err != nil {
			log.Fatalf("FATAL: Error uploading object %s: %v", objectname, err)
		}
	}
	// Remember last done time
	upload_finish = time.Now()
	// One less thread
	atomic.AddInt32(&running_threads, -1)
}

func runDownload(thread_num int) {
	client := getS3Client()
	for time.Now().Before(endtime) {
		atomic.AddInt32(&download_count, 1)
		n := rand.Int31n(upload_count)
		objectname := fmt.Sprintf("Object-%d", n)
		input := &s3.GetObjectInput{
			Bucket: aws.String(bucket),
			Key:    aws.String(objectname),
		}
		res, err := client.GetObject(context.TODO(),
			input,
			func(u *s3.Options) {
				u.UsePathStyle = true
			})
		if err != nil {
			log.Fatalf("FATAL: Error downloading object %s: %v", objectname, err)
		}
		io.Copy(ioutil.Discard, res.Body)
	}
	// Remember last done time
	download_finish = time.Now()
	// One less thread
	atomic.AddInt32(&running_threads, -1)
}

func runDelete(thread_num int) {
	client := getS3Client()
	for {
		n := atomic.AddInt32(&delete_count, 1)
		if n > upload_count {
			break
		}
		objectname := fmt.Sprintf("Object-%d", n)
		input := &s3.DeleteObjectInput{
			Bucket: aws.String(bucket),
			Key:    aws.String(objectname),
		}
		_, err := client.DeleteObject(context.TODO(),
			input,
			func(u *s3.Options) {
				u.UsePathStyle = true
			})
		if err != nil {
			log.Fatalf("FATAL: Error deleting object %s: %v", objectname, err)
		}
	}
	// Remember last done time
	delete_finish = time.Now()
	// One less thread
	atomic.AddInt32(&running_threads, -1)
}

func main() {
	// Hello
	fmt.Println("Wasabi benchmark program v2.0 (simplified)")

	// Parse command line
	myflag := flag.NewFlagSet("myflag", flag.ExitOnError)
	myflag.StringVar(&access_key, "a", "", "Access key")
	myflag.StringVar(&secret_key, "s", "", "Secret key")
	myflag.StringVar(&url_host, "u", "http://s3.wasabisys.com", "URL for host with method prefix")
	myflag.StringVar(&bucket, "b", "wasabi-benchmark-bucket", "Bucket for testing")
	myflag.StringVar(&region, "r", "us-east-1", "Region for testing")
	myflag.IntVar(&duration_secs, "d", 30, "Duration of each test in seconds")
	myflag.IntVar(&threads, "t", 1, "Number of threads to run")
	myflag.IntVar(&loops, "l", 1, "Number of times to repeat test")
	var sizeArg string
	myflag.StringVar(&sizeArg, "z", "1M", "Size of objects in bytes with postfix K, M, and G")
	if err := myflag.Parse(os.Args[1:]); err != nil {
		os.Exit(1)
	}

	// Check the arguments
	if access_key == "" {
		log.Fatal("Missing argument -a for access key.")
	}
	if secret_key == "" {
		log.Fatal("Missing argument -s for secret key.")
	}
	var err error
	if object_size, err = bytefmt.ToBytes(sizeArg); err != nil {
		log.Fatalf("Invalid -z argument for object size: %v", err)
	}

	// Echo the parameters
	logit(fmt.Sprintf("Parameters: url=%s, bucket=%s, region=%s, duration=%d, threads=%d, loops=%d, size=%s",
		url_host, bucket, region, duration_secs, threads, loops, sizeArg))

	// Initialize data for the bucket
	object_data = make([]byte, object_size)
	rand.Read(object_data)
	hasher := md5.New()
	hasher.Write(object_data)
	object_data_md5 = base64.StdEncoding.EncodeToString(hasher.Sum(nil))

	// Create the bucket and delete all the objects
	//createBucket(true)
	//deleteAllObjects()

	// Loop running the tests
	for loop := 1; loop <= loops; loop++ {

		// reset counters
		upload_count = 0
		upload_slowdown_count = 0
		download_count = 0
		download_slowdown_count = 0
		delete_count = 0
		delete_slowdown_count = 0

		// Run the upload case
		running_threads = int32(threads)
		starttime := time.Now()
		endtime = starttime.Add(time.Second * time.Duration(duration_secs))
		for n := 1; n <= threads; n++ {
			go runUpload(n)
		}

		// Wait for it to finish
		for atomic.LoadInt32(&running_threads) > 0 {
			time.Sleep(time.Millisecond)
		}
		upload_time := upload_finish.Sub(starttime).Seconds()

		bps := float64(uint64(upload_count)*object_size) / upload_time
		logit(fmt.Sprintf("Loop %d: PUT time %.1f secs, objects = %d, speed = %sB/sec, %.1f operations/sec. Slowdowns = %d",
			loop, upload_time, upload_count, bytefmt.ByteSize(uint64(bps)), float64(upload_count)/upload_time, upload_slowdown_count))

		// Run the download case
		running_threads = int32(threads)
		starttime = time.Now()
		endtime = starttime.Add(time.Second * time.Duration(duration_secs))
		for n := 1; n <= threads; n++ {
			go runDownload(n)
		}

		// Wait for it to finish
		for atomic.LoadInt32(&running_threads) > 0 {
			time.Sleep(time.Millisecond)
		}
		download_time := download_finish.Sub(starttime).Seconds()

		bps = float64(uint64(download_count)*object_size) / download_time
		logit(fmt.Sprintf("Loop %d: GET time %.1f secs, objects = %d, speed = %sB/sec, %.1f operations/sec. Slowdowns = %d",
			loop, download_time, download_count, bytefmt.ByteSize(uint64(bps)), float64(download_count)/download_time, download_slowdown_count))

		// Run the delete case
		running_threads = int32(threads)
		starttime = time.Now()
		endtime = starttime.Add(time.Second * time.Duration(duration_secs))
		for n := 1; n <= threads; n++ {
			go runDelete(n)
		}

		// Wait for it to finish
		for atomic.LoadInt32(&running_threads) > 0 {
			time.Sleep(time.Millisecond)
		}
		delete_time := delete_finish.Sub(starttime).Seconds()

		logit(fmt.Sprintf("Loop %d: DELETE time %.1f secs, %.1f deletes/sec. Slowdowns = %d",
			loop, delete_time, float64(upload_count)/delete_time, delete_slowdown_count))
	}

	// All done
}
