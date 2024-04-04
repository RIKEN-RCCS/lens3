/* Lens3-Mux implementation. */

// Copyright 2022-2024 RIKEN R-CCS.
// SPDX-License-Identifier: BSD-2-Clause

// Package multiplexer provides a proxy to a backend S3 server.

package lens3

import (
	"fmt"
	//"flag"
	"io"
	"log"
	//"net"
	"net/http"
	"net/http/httputil"
	"net/url"
	//"time"
	"runtime"
)

func handler(w http.ResponseWriter, r1 *http.Request) {
	//w.Header().Set("Content-Type", "text/plain")
	//w.Header().Set("Content-Length", string(len(result)))
	fmt.Fprintf(w, "Hello, World")

	client := &http.Client{}
	r2 := r1.Clone(r1.Context())
	//r2.RequestURI = ""

	res, err := client.Do(r2)
	if err != nil {
		http.Error(w, "Server Error", http.StatusInternalServerError)
		log.Fatal("ServeHTTP:", err)
	}
	defer res.Body.Close()

	log.Println(r2.RemoteAddr, " ", res.Status)

	for k, vv := range res.Header {
		for _, v := range vv {
			w.Header().Add(k, v)
		}
	}
	w.WriteHeader(res.StatusCode)
	io.Copy(w, res.Body)
}

func main_() {
	runtime.GOMAXPROCS(runtime.NumCPU())
	/*
		http.HandleFunc("/", handler)
		http.ListenAndServe(":8080", nil)
	*/
	/*
		http.HandleFunc("/", handler)
		srv := &http.Server{
			Addr:        ":8080",
			Handler:     http.DefaultServeMux,
			ReadTimeout: time.Duration(5) * time.Second,
		}
		srv.ListenAndServe()
	*/
	s1, _ := url.Parse("http://localhost:9004")
	proxy := httputil.NewSingleHostReverseProxy(s1)
	http.ListenAndServe(":8080", proxy)
}
