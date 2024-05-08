/* Lens3-Mux Main. */

// Copyright 2022-2024 RIKEN R-CCS.
// SPDX-License-Identifier: BSD-2-Clause

// Multiplexer is a proxy to a backend S3 server.  Lens3 main part.

// MEMO:
//
// func (f HandlerFunc) ServeHTTP(w http.ResponseWriter, r *http.Request)
// func (p *ReverseProxy) ServeHTTP(rw http.ResponseWriter, req *http.Request)
//
// http.HandlerFunc is a function type.  It is
// (ResponseWriter,*Request) -> unit

package lens3

import (
	"fmt"
	//"flag"
	//"context"
	//"io"
	"log"
	"os"
	//"net"
	"net/http"
	"net/http/httputil"
	"net/url"
	//"strings"
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

	mux_addrs []string /*sorted*/
	//mux_addrs = m.list_mux_ip_addresses()

	multiplexer_conf

	backend_common
}

type multiplexer_conf struct {
	mux_node_name string

	front_host      string
	trusted_proxies []string /*sorted*/
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

func start_multiplexer(m *multiplexer) {
	fmt.Println("start_proxy() 8005->9001")
	m.forwarding_timeout = 60
	//m.client = &http.Client{}
	//m.proxy = m.client
	m.front_host = "localhost"

	var proxy1 = make_proxy_2(m)
	var proxy2 = filter_forwarding(m, proxy1)
	var err2 = http.ListenAndServe(":8005", proxy2)
	log.Fatal(err2)
}

func list_mux_ip_addresses(m *multiplexer) []string {
	//muxs = m.tables.list_mux_eps()
	var muxs = []string{}
	var ips []string
	for _, h := range muxs {
		var x = get_ip_addresses(h)
		ips = append(ips, x...)
	}
	return ips
}

func filter_forwarding(m *multiplexer, following http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		ensure_forwarding_host_trusted(m, r)
		//http.Error(w, "ERROR!", http.StatusMethodNotAllowed)
		ensure_pool_state(m, r)
		ensure_user_is_authorized(m, r)
		ensure_secret_owner(m, r)
		ensure_bucket_policy(m, r)
		logger.error(("Mux ({m._mux_host}) Got a request from" +
			" untrusted proxy or unknonwn Mux: {peer_addr};" +
			" Check configuration"))
		following.ServeHTTP(w, r)
	})
}

// It double checks m.mux_addrs, because mux_addrs is updated only
// when necessary.
func ensure_forwarding_host_trusted(m *multiplexer, r *http.Request) bool {
	var peer_addr = r.Header.Get("REMOTE_ADDR")
	if peer_addr == "" {
		return false
	}
	var ip = make_typical_ip_address(peer_addr)
	if string_search(ip, m.trusted_proxies) ||
		string_search(ip, m.mux_addrs) {
		return true
	}
	m.mux_addrs = list_mux_ip_addresses(m)
	if string_search(ip, m.mux_addrs) {
		return true
	}
	return false
}

// Performs a very weak check that a bucket accepts any public access
// or an access has an access-key.
func ensure_bucket_policy(m *multiplexer, r *http.Request) bool {
	/*
		    pool_id = desc["pool"]
		    policy = desc["bkt_policy"]
		    if policy in {"public", "download", "upload"} {
		        # ANY PUBLIC ACCESS ARE PASSED.
		        return
			} elif access_key is not None {
		        # JUST CHECK AN ACEESS IS WITH A KEY.
		        return
				}
		    raise Api_Error(401, f"Access-key missing")
	*/
	return true
}

func ensure_user_is_authorized(m *multiplexer, r *http.Request) bool {
	/*
		    u = tables.get_user(user_id)
		    assert u is not None
		    if not u.get("enabled") {
				raise Api_Error(403, (f"User disabled: {user_id}"))
			}
	*/
	return true
}

func ensure_secret_owner(m *multiplexer, r *http.Request) bool {
	/*
		    u = tables.get_user(user_id)
		    assert u is not None
		    if not u.get("enabled") {
		        raise Api_Error(403, (f"User disabled: {user_id}"))
			}
	*/
	return true
}

func ensure_mux_is_running(m *multiplexer, r *http.Request) bool {
	/*
		    muxs = tables.list_mux_eps()
		    if len(muxs) == 0 {
		        raise Api_Error(500, (f"No Mux services in Lens3"))
			}
	*/
	return true
}

func ensure_pool_state(m *multiplexer, r *http.Request) bool {
	/*
		    (state, reason) = update_pool_state(tables, pool_id)
		    if state == Pool_State.INITIAL {
		        if reject_initial_state {
		            logger.error(f"Manager (pool={pool_id}) is in initial state.")
		            raise Api_Error(403, f"Pool is in initial state")
				}
		    } elif state == Pool_State.READY {
		        pass
		    } elif state == Pool_State.SUSPENDED {
		        raise Api_Error(503, f"Pool suspended")
		    } elif state == Pool_State.DISABLED {
		        raise Api_Error(403, f"Pool disabled")
		    } elif state == Pool_State.INOPERABLE {
		        raise Api_Error(403, f"Pool inoperable")
		    } else {
		        assert False
			}
	*/
	return true
}

/*
func (m *backend_proxy) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	var proc = m.get_super_part()
	var failure_message = fmt.Sprintf(
		("Mux ({self._mux_host}) urlopen failure:" +
			" url={url} for {request_method} {request_url};"))
	_ = failure_message

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
*/

// MEMO: net.http.httputil.ReverseProxy implements ServeHTTP().

func make_proxy_1(m *multiplexer) http.Handler {
	fmt.Println("make_proxy_1() 8005->9001")
	var url1, err1 = url.Parse("http://localhost:9001")
	assert_fatal(err1 == nil)
	var proxy = httputil.NewSingleHostReverseProxy(url1)
	return proxy
}

func make_proxy_2(m *multiplexer) http.Handler {
	fmt.Println("make_proxy_2() 8005->9001")
	var proxy = httputil.ReverseProxy{
		Rewrite: func(r *httputil.ProxyRequest) {
			var url1, err1 = url.Parse("http://localhost:9001")
			assert_fatal(err1 == nil)
			r.SetURL(url1)
			r.SetXForwarded()
		},
	}
	return &proxy
}

func start_example_proxy_() {
	fmt.Println("start_example_proxy() 8005->9001")
	var url1, err1 = url.Parse("http://localhost:9001")
	assert_fatal(err1 == nil)
	var proxy = httputil.NewSingleHostReverseProxy(url1)
	var err2 = http.ListenAndServe(":8005", proxy)
	log.Fatal(err2)
}
