/* Lens3-Mux Main. */

// Copyright 2022-2024 RIKEN R-CCS.
// SPDX-License-Identifier: BSD-2-Clause

// Multiplexer is a proxy to a backend S3 server.

package lens3

import (
	"fmt"
	//"flag"
	"context"
	"io"
	"log"
	"os"
	//"net"
	"net/http"
	"net/http/httputil"
	"net/url"
	"strings"
	"time"
	//"runtime"
)

// MULTIPLEXER is a single object, "the_multiplexer".  It is
// with threads of a child process reaper.
type multiplexer struct {

	// BE factory is to make a backend.
	be backend_factory

	// PROC maps a PID to a process record.  PID is int in "os".
	proc map[int]backend

	// CH_SIG is a channel to receive SIGCHLD.
	ch_sig chan os.Signal

	environ []string

	// CLIENT accesses backend servers.
	client http.Client

	//proxy *backend_proxy

	multiplexer_conf

	backend_common
}

type multiplexer_conf struct {
	mux_node_name string

	front_host      string
	trusted_proxies []string
	front_host_ip   string

	mux_ep_update_interval time.Duration
	periodic_work_interval time.Duration
	mux_expiry             time.Duration

	forwarding_timeout   time.Duration
	probe_access_timeout time.Duration
	bad_response_delay   time.Duration
	busy_suspension_time time.Duration
}

type backend_proxy struct {
	backend
	multiplexer
	client *http.Client
}

// THE_MULTIPLEXER is the single multiplexer instance.
var the_multiplexer = multiplexer{
	proc: make(map[int]backend),
}

/*
func handler_(w http.ResponseWriter, r1 *http.Request) {
	//w.Header().Set("Content-Type", "text/plain")
	//w.Header().Set("Content-Length", string(len(result)))
	fmt.Fprintf(w, "Hello, World")

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
*/

func start_multiplexer(m *multiplexer) {
	fmt.Println("start_proxy() 8005->9001")
	m.forwarding_timeout = 60
	//m.client = &http.Client{}
	//m.proxy = m.client
	m.front_host = "localhost"

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

	h1 := func(w http.ResponseWriter, _ *http.Request) {
		io.WriteString(w, "Hello from a HandleFunc #1!\n")
	}
	h2 := func(w http.ResponseWriter, _ *http.Request) {
		io.WriteString(w, "Hello from a HandleFunc #2!\n")
	}

	http.HandleFunc("/", h1)
	http.HandleFunc("/endpoint", h2)

	var err2 = http.ListenAndServe(":8005", nil)
	log.Fatal(err2)
}

func (m *backend_proxy) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	var proc = m.get_super_part()
	var /*failure_message*/ _ = fmt.Sprintf(
		("Mux ({self._mux_host}) urlopen failure:" +
			" url={url} for {request_method} {request_url};"))

	// Copy request headers.  Do not use Add or Set.  Set "HOST" in
	// case it is missing.

	var q_headers http.Header
	for k1, v1 := range r.Header {
		if strings.HasPrefix(k1, "HTTP_") {
			var k2 = strings.Replace(k1[5:], "_", "-", -1)
			var k3 = http.CanonicalHeaderKey(k2)
			q_headers[k3] = v1
		}
	}
	q_headers.Add("HOST", m.front_host)
	var content_type = r.Header.Get("CONTENT_TYPE")
	if content_type != "" {
		q_headers.Set("CONTENT-TYPE", content_type)
	}
	var content_length = r.Header.Get("CONTENT_LENGTH")
	if content_length != "" {
		q_headers.Set("CONTENT-LENGTH", content_length)
	}

	var url = fmt.Sprintf("http://%s/%s?%s",
		proc.ep,
		r.URL.Path,
		r.URL.RawQuery)
	var body io.Reader = r.Body
	var method string = r.Method
	var timeout = time.Duration(m.forwarding_timeout * time.Second)
	var ctx, cancel = context.WithTimeout(context.Background(), timeout)
	defer cancel()
	var req2, err2 = http.NewRequestWithContext(ctx, method, url, body)
	assert_fatal(err2 != nil)
	req2.Header = q_headers
	// (rsp : *http.Response)
	var rsp, err3 = m.client.Do(req2)
	assert_fatal(err3 != nil)
	var r_headers = w.Header()
	for k4, v4 := range rsp.Header {
		r_headers[k4] = v4
	}
}

// ensure_user_is_authorized(self.tables, user_id)
// ensure_pool_state(self.tables, pool_id, False)
// ensure_secret_owner(self.tables, access_key, pool_id)
// ensure_bucket_policy(bucket, bucketdesc, access_key)

type check_forwarding_host_trusted struct {
	backend
	next http.Handler
}

func (m *check_forwarding_host_trusted) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	/*
		if peer_addr is None {
			return False
		}
		ip = make_typical_ip_address(peer_addr)
		if (ip in self._trusted_proxies or ip in self._mux_addrs) {
			return True
		}
		self._mux_addrs = self._list_mux_ip_addresses()
		if ip in self._mux_addrs {
			return True
		}
		return False
	*/

	if false {
		logger.error(("Mux ({m._mux_host}) Got a request from" +
			" untrusted proxy or unknonwn Mux: {peer_addr};" +
			" Check configuration"))
		log_access("403", "")
		raise(api_error(403, "Bad access from remote={client_addr}"))
	}
	m.next.ServeHTTP(w, r)
}

/*
func make_proxy() {
	var proxy = httputil.ReverseProxy{
		Rewrite: func(r *httputil.ProxyRequest) {
			r.SetXForwarded()
			r.SetURL(rpURL)
		},
	}
}
*/

func start_dummy_proxy(m *multiplexer) {
	fmt.Println("start_dummy_proxy() 8005->9001")
	var url1, err1 = url.Parse("http://localhost:9001")
	assert_fatal(err1 == nil)
	var proxy = httputil.NewSingleHostReverseProxy(url1)
	var err2 = http.ListenAndServe(":8005", proxy)
	fmt.Println("http.ListenAndServe=", err2)
}
