/* sporadic.go */

// It runs uploading/downloading periodically.  That tests on
// starting/stopping a backend server, which is a critical part in
// Lens3's work.

package main

import (
	"bytes"
	"context"
	crand "crypto/rand"
	"encoding/json"
	"fmt"
	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/config"
	"github.com/aws/aws-sdk-go-v2/credentials"
	"github.com/aws/aws-sdk-go-v2/service/s3"
	"io/ioutil"
	"log"
	"math/rand/v2"
	"sync"
	"time"
	//"io"
)

type s3client struct {
	url    string
	bucket string
	client *s3.Client
}

type testconf struct {
	S3_ep       string       `json:"s3_ep"`
	Size        int          `json:"size"`
	Count       int          `json:"count"`
	Threads     int          `json:"threads"`
	Period      int          `json:"period"`
	Fluctuation int          `json:"fluctuation"`
	Stores      []*storeconf `json:"stores"`
}

type storeconf struct {
	Bucket     string `json:"bucket"`
	Access_key string `json:"access_key"`
	Secret_key string `json:"secret_key"`
}

func make_clients(ep string, stores []*storeconf) []s3client {
	clients := make([]s3client, 0, len(stores))
	for _, s := range stores {
		var url = ep
		var bucket = s.Bucket
		customresolver := aws.EndpointResolverWithOptionsFunc(
			func(service, region string, options ...interface{}) (aws.Endpoint, error) {
				return aws.Endpoint{
					URL:           url,
					SigningRegion: region,
				}, nil
			})
		var access_key = s.Access_key
		var secret_key = s.Secret_key
		var cfg, err2 = config.LoadDefaultConfig(context.TODO(),
			config.WithEndpointResolverWithOptions(customresolver),
			config.WithCredentialsProvider(
				credentials.NewStaticCredentialsProvider(access_key, secret_key,
					"")))
		if err2 != nil {
			log.Fatalf("Fail to read a client configuration.")
		}
		var client = s3.NewFromConfig(cfg)
		if client == nil {
			log.Fatalf("Fail to create a S3 client.")
		}
		var e = s3client{url, bucket, client}
		clients = append(clients, e)
	}
	return clients
}

func upload_files(wg *sync.WaitGroup, client s3client, data []byte, count int, tid int) {
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

func download_files(wg *sync.WaitGroup, client s3client, gooddata []byte, count int, tid int) {
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
	var b, err0 = ioutil.ReadFile("testconf.json")
	if err0 != nil {
		log.Fatalf("Failure in reading testconf.json: %v", err0)
	}
	var conf testconf
	var err1 = json.Unmarshal(b, &conf)
	if err1 != nil {
		log.Fatalf("Failure in parsing testconf.json: %v", err1)
	}
	fmt.Println("testconf=", conf)
	//var base = testconf["s3"].(string)
	//var size = int(testconf["size"].(float64))
	//var count = int(testconf["count"].(float64))
	//var threads = int(testconf["threads"].(float64))
	//var period = testconf["period"].(float64)
	//var fluctuation = testconf["fluctuation"].(float64)
	//var stores = testconf["stores"].([]interface{})
	var clients = make_clients(conf.S3_ep, conf.Stores)
	fmt.Println("clients=", clients)

	var data = make([]byte, conf.Size)
	crand.Read(data)

	var wg sync.WaitGroup

	for true {
		fmt.Println("Running uploading/downloading at",
			time.Now().Format(time.RFC3339), "...")
		for _, client := range clients {
			for tid := 0; tid < conf.Threads; tid++ {
				wg.Add(1)
				go upload_files(&wg, client, data, conf.Count, tid)
			}
		}
		wg.Wait()
		for _, client := range clients {
			for tid := 0; tid < conf.Threads; tid++ {
				wg.Add(1)
				go download_files(&wg, client, data, conf.Count, tid)
			}
		}
		wg.Wait()
		var f = ((float64(conf.Fluctuation) / 100.0) *
			(2.0*rand.Float64() - 1.0))
		var d = (float64(conf.Period) * (1.0 + f))
		var sec = (time.Duration(float64(conf.Period)*d) * time.Second)
		fmt.Println("Sleeping in", sec, "...")
		time.Sleep(sec)
	}
}
