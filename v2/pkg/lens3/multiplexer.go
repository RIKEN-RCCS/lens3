/* Lens3-Mux Main. */

// Copyright 2022-2024 RIKEN R-CCS.
// SPDX-License-Identifier: BSD-2-Clause

package lens3

// Multiplexer is a proxy to a backend S3 server.  Lens3 main part.

// MEMO:
//
// func (f HandlerFunc) ServeHTTP(w http.ResponseWriter, r *http.Request)
// func (p *ReverseProxy) ServeHTTP(rw http.ResponseWriter, req *http.Request)
//
// http.HandlerFunc is a function type.  It is
// (ResponseWriter,*Request) -> unit

import (
	"fmt"
	//"flag"
	//"context"
	//"io"
	"log"
	//"os"
	"net"
	//"maps"
	"net/http"
	"net/http/httputil"
	"net/url"
	"os"
	"strconv"
	"strings"
	"time"
	//"runtime"
)

// MULTIPLEXER is a single object, "the_multiplexer".  It is
// with threads of a child process reaper.
type multiplexer struct {
	table *keyval_table

	// MUX_EP and MUX_PID are about a process that a multiplexer and a
	// manager run in.
	mux_ep  string
	mux_pid int

	verbose bool

	// BE factory is to make a backend.
	//be backend_factory

	// POOL maps a POOL-ID to a process record.
	//pool map[string]backend

	// PROC maps a PID to a process record.  PID is int in "os".
	//proc map[int]backend

	// CH_SIG is a channel to receive SIGCHLD.
	//ch_sig chan os.Signal

	// ??? CLIENT accesses backend servers.
	client http.Client

	//proxy *backend_proxy

	// MUX_ADDRS is a sorted list of ip adrresses.
	mux_addrs []string
	// mux_addrs = m.list_mux_ip_addresses()

	// UNKNOW FIELDS OF Multiplexer_conf.
	// front_host_ip?
	// periodic_work_interval?
	// mux_expiry?

	multiplexer_conf
}

// type backend_proxy struct {
// 	backend
// 	multiplexer
// 	client *http.Client
// }

// THE_MULTIPLEXER is the single multiplexer instance.
var the_multiplexer = multiplexer{
	//pool: make(map[string]backend),
	//proc: make(map[int]backend),
}

const (
	empty_payload_hash_sha256 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
)

const (
	backend_not_running    = "backend not running"
	no_bucket_name_in_url  = "no bucket name in url"
	bad_bucket_name_in_url = "bad_bucket_name_in_url"
	bad_signature          = "bad signature"
	no_named_bucket        = "no_named_bucket"
)

func init_multiplexer(m *multiplexer, t *keyval_table, conf *mux_conf) {
	m.table = t
	m.multiplexer_conf = conf.Multiplexer

	var host string
	if m.multiplexer_conf.Mux_node_name != "" {
		host = m.multiplexer_conf.Mux_node_name
	} else {
		var h, err1 = os.Hostname()
		if err1 != nil {
			panic(err1)
		}
		host = h
	}
	var port = m.multiplexer_conf.Port
	m.mux_ep = net.JoinHostPort(host, strconv.Itoa(port))
	m.mux_pid = os.Getpid()
}

func start_service_for_test() {
	var dbconf = read_db_conf("conf.json")
	var t = make_table(dbconf)
	var muxconf = get_mux_conf(t, "mux")
	var apiconf = get_api_conf(t, "api")
	_ = apiconf

	var m = &the_multiplexer
	init_multiplexer(m, t, muxconf)

	var w = &the_manager
	init_manager(w, t, m, muxconf)
	go start_manager(w)

	time.Sleep(5 * time.Second)

	if true {
		var g = start_backend_for_test(w)
		var proc = g.get_super_part()
		//var pool = proc.Pool

		var desc = &proc.backend_record
		fmt.Println("set_backend_process(2) ep=", proc.Backend_ep)
		fmt.Println("proc.backend_record=")
		print_in_json(desc)
		set_backend_process(w.table, proc.Pool, desc)
		//var proc = g.get_super_part()
		//m.pool[proc.pool] = g
		//time.Sleep(30 * time.Second)
		//start_dummy_proxy(m)
	}

	start_multiplexer(m)
}

func start_multiplexer(m *multiplexer) {
	fmt.Println("start_multiplexer()")
	m.Forwarding_timeout = 60
	//m.client = &http.Client{}
	//m.proxy = m.client
	m.Front_host = "localhost"

	// MEMO: ReverseProxy <: Handler as it implements ServeHTTP().
	var proxy1 = httputil.ReverseProxy{
		Rewrite: proxy_request_rewriter(m),
	}
	var proxy2 = make_forwarding_proxy(m, &proxy1)
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

// PROXY_REQUEST_REWRITER is a function set in ReverseProxy.Rewriter.
// It receives forwarding information from a forwarding-proxy via a
// http header field "lens3-pool".
func proxy_request_rewriter(m *multiplexer) func(r *httputil.ProxyRequest) {
	return func(r *httputil.ProxyRequest) {
		var x = r.In.Header["lens3-pool"]
		assert_fatal(len(x) == 1)
		var pool = x[0]
		delete(r.In.Header, "lens3-pool")
		delete(r.Out.Header, "lens3-pool")
		var be = get_backend_process(m.table, pool)
		if be == nil {
			logger.debug("Mux({pool}).")
			raise(&proxy_exc{http_status_404_not_found, "pool non-exist"})
		}
		fmt.Println("*** POOL=", pool, " BE=", be)
		//var g = m.pool[pool]
		//var proc = g.get_super_part()
		var url1, err1 = url.Parse("http://" + be.Backend_ep)
		if err1 != nil {
			logger.debugf("Mux(pool=%s) bad backend url: err=(%v)", pool, err1)
			raise(&proxy_exc{http_status_500_internal_server_error,
				"bad url"})
		}
		fmt.Println("*** URL=", url1)
		r.SetURL(url1)
		r.SetXForwarded()
	}
}

// MAKE_FORWARDING_PROXY makes a filter that checks an access is
// granted.  It passes the request to the next handler PROXY, after
// signing it with a backend credential.  It embeds some information
// under an http header "lens3-pool" for the next handler.  See
// proxy_request_rewriter.
func make_forwarding_proxy(m *multiplexer, proxy http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		//var g = m.pool["mMwfyMzLwOlb8QLYANRM"]
		//var proc = g.get_super_part()
		//var proc = get_backend_process(m.table, "mMwfyMzLwOlb8QLYANRM")
		//fmt.Println("*** POOL=", pool)

		var authenticated = check_authenticated(m, r)
		if authenticated == "" {
			//http.Error(w, "BAD", http_status_401_unauthorized)
			log_access(400, r)
			raise(&proxy_exc{http_status_401_unauthorized,
				bad_signature})
		}

		// var bucketname = pick_bucket_in_path(m, r)
		var bucketname = "lenticularis-oddity-a1"

		var bucket = get_bucket(m.table, bucketname)
		if bucket == nil {
			log_access(400, r)
			raise(&proxy_exc{http_status_404_not_found,
				no_named_bucket})
		}

		var pool = "d4f0c4645fce5734"
		//var pool = generate_pool_name()
		var desc = get_backend_process(m.table, pool)
		logger.debugf("Mux(pool=%s) backend=%v.", pool, desc)
		if desc == nil {
			http.Error(w, "BAD", http_status_500_internal_server_error)
			raise(&proxy_exc{http_status_500_internal_server_error,
				backend_not_running})
		}

		ensure_forwarding_host_trusted(m, r)
		//http.Error(w, "ERROR!", http.StatusMethodNotAllowed)
		ensure_pool_state(m, r)
		ensure_user_is_authorized(m, r)
		ensure_secret_owner(m, r)
		ensure_bucket_policy(m, r)
		//logger.error(("Mux ({m._mux_host}) Got a request from" +
		//	" untrusted proxy or unknonwn Mux: {peer_addr};" +
		//	" Check configuration"))

		/* Replace an authorization header. */

		sign_by_backend_credential(r, desc)

		r.Header["lens3-pool"] = []string{pool}
		proxy.ServeHTTP(w, r)
	})
}

func check_authenticated(m *multiplexer, r *http.Request) string {
	var a1 = r.Header.Get("Authorization")
	var a2 s3v4_authorization = scan_aws_authorization(a1)
	var key string
	if a2.signature != "" {
		key = a2.credential[0]
	} else {
		key = ""
	}

	var keypair = [2]string{
		"yDRzcPdqHkwupPqryAvO",
		"ZNDov7ZJ5ecAksaJHaUxmoWwNOb52ZYj3lAdTq1lmkJGqaMx",
	}

	var ok = check_credential_in_request(m.verbose, r, keypair)
	if ok {
		return key
	} else {
		return ""
	}
}

// It double checks m.mux_addrs, because mux_addrs is updated only
// when necessary.
func ensure_forwarding_host_trusted(m *multiplexer, r *http.Request) bool {
	var peer_addr = r.Header.Get("REMOTE_ADDR")
	if peer_addr == "" {
		return false
	}
	var ip = make_typical_ip_address(peer_addr)
	if string_search(ip, m.Trusted_proxies) ||
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

func pick_bucket_in_path(m *multiplexer, r *http.Request) string {
	var u1 = r.URL
	var path = strings.Split(u1.EscapedPath(), "/")
	if len(path) >= 2 && path[0] != "" {
		raise(&proxy_exc{http_status_400_bad_request,
			no_bucket_name_in_url})
	}
	var bucket = path[1]
	if bucket == "" {
		log_access(400, r)
		raise(&proxy_exc{http_status_400_bad_request,
			no_bucket_name_in_url})
	}
	if !check_bucket_naming(bucket) {
		log_access(400, r)
		raise(&proxy_exc{http_status_400_bad_request,
			bad_bucket_name_in_url})
	}
	return bucket
}
