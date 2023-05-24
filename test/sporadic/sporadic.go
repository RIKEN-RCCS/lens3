/* sporadic.go */

/* Runs uploading/downloading periodically.  It tests on
   starting/stopping MinIO, which is a critical part of Lens3. */

package main

import (
	"bytes"
	"context"
	"fmt"
	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/config"
	"github.com/aws/aws-sdk-go-v2/credentials"
	"github.com/aws/aws-sdk-go-v2/service/s3"
	//"io"
	"encoding/json"
	"io/ioutil"
	"log"
	"math/rand"
	"sync"
	"time"
)

type S3c struct {
	url    string
	bucket string
	client *s3.Client
}

func make_clients(base string, stores []interface{}) []S3c {
	clients := make([]S3c, 0, len(stores))
	for _, s0 := range stores {
		s := s0.(map[string]interface{})
		url := base
		bucket := s["bucket"].(string)
		customresolver := aws.EndpointResolverWithOptionsFunc(
			func(service, region string, options ...interface{}) (aws.Endpoint, error) {
				return aws.Endpoint{
					URL:           url,
					SigningRegion: region,
				}, nil
			})
		access_key := s["access_key"].(string)
		secret_key := s["secret_key"].(string)
		cfg, err2 := config.LoadDefaultConfig(context.TODO(),
			config.WithEndpointResolverWithOptions(customresolver),
			config.WithCredentialsProvider(
				credentials.NewStaticCredentialsProvider(access_key, secret_key,
					"")))
		if err2 != nil {
			log.Fatalf("Fail to read a client configuration.")
		}
		client := s3.NewFromConfig(cfg)
		if client == nil {
			log.Fatalf("Fail to create a S3 client.")
		}
		e := S3c{url, bucket, client}
		clients = append(clients, e)
	}
	return clients
}

func upload_files(wg *sync.WaitGroup, client S3c, data []byte, count int, tid int) {
	defer wg.Done()
	for i := 1; i < count; i++ {
		objectname := fmt.Sprintf("gomi-%d-%d", tid, i)
		file := bytes.NewReader(data)
		input := &s3.PutObjectInput{
			Bucket: aws.String(client.bucket),
			Key:    aws.String(objectname),
			Body:   file,
		}
		_, err := client.client.PutObject(context.TODO(),
			input,
			func(u *s3.Options) {
				u.UsePathStyle = true
			})
		if err != nil {
			log.Fatalf("Failure in uploading an object %s: %v",
				objectname, err)
		}
	}
}

func download_files(wg *sync.WaitGroup, client S3c, gooddata []byte, count int, tid int) {
	defer wg.Done()
	for i := 1; i < count; i++ {
		objectname := fmt.Sprintf("gomi-%d-%d", tid, i)
		input := &s3.GetObjectInput{
			Bucket: aws.String(client.bucket),
			Key:    aws.String(objectname),
		}
		res, err0 := client.client.GetObject(context.TODO(),
			input,
			func(u *s3.Options) {
				u.UsePathStyle = true
			})
		if err0 != nil {
			log.Fatalf("Failure in downloading an object %s: %v",
				objectname, err0)
		}
		//io.Copy(data, res.Body)
		data, err1 := ioutil.ReadAll(res.Body)
		if err1 != nil {
			log.Fatalf("Failure in downloading an object: %v", err1)
		}
		if !bytes.Equal(data, gooddata) {
			log.Fatalf("Failure in downloading an object (wrong data)")
		}
	}
}

func main() {
	//log.SetFlags(log.LstdFlags | log.Lshortfile)
	b, err0 := ioutil.ReadFile("testc.json")
	if err0 != nil {
		log.Fatalf("Failure in reading testc.json: %v", err0)
	}
	var testc map[string]interface{}
	err1 := json.Unmarshal(b, &testc)
	if err1 != nil {
		log.Fatalf("Failure in parsing testc.json: %v", err1)
	}
	fmt.Println("testc=", testc)
	base := testc["s3"].(string)
	size := int(testc["size"].(float64))
	count := int(testc["count"].(float64))
	threads := int(testc["threads"].(float64))
	period := testc["period"].(float64)
	fluctuation := testc["fluctuation"].(float64)

	stores := testc["stores"].([]interface{})
	clients := make_clients(base, stores)
	fmt.Println("clients=", clients)

	data := make([]byte, size)
	rand.Read(data)

	var wg sync.WaitGroup

	for true {
		fmt.Println("Running uploading/downloading at",
			time.Now().Format(time.RFC3339), "...")
		for _, client := range clients {
			for tid := 0; tid < threads; tid++ {
				wg.Add(1)
				go upload_files(&wg, client, data, count, tid)
			}
		}
		wg.Wait()
		for _, client := range clients {
			for tid := 0; tid < threads; tid++ {
				wg.Add(1)
				go download_files(&wg, client, data, count, tid)
			}
		}
		wg.Wait()
		sec := (time.Duration(period*(1.0+(fluctuation/100.0)*(2.0*rand.Float64()-1.0))) * time.Second)
		fmt.Println("Sleeping in", sec, "...")
		time.Sleep(sec)
	}
}
