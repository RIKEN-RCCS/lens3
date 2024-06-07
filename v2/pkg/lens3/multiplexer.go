/* Lens3-Mux Main. */

// Copyright 2022-2024 RIKEN R-CCS.
// SPDX-License-Identifier: BSD-2-Clause

package lens3

// Multiplexer is a proxy to a backend S3 server.  Lens3 main part.

// MEMO:
//
// func (f HandlerFunc) ServeHTTP(w http.ResponseWriter, r *http.Request)
// func (p *ReverseProxy) ServeHTTP(w http.ResponseWriter, r *http.Request)
//
// http.HandlerFunc is a function type.  It is
// (ResponseWriter,*Request)→unit

import (
	"fmt"
	//"flag"
	//"context"
	"runtime/debug"
	//"io"
	"encoding/json"
	//"log"
	//"os"
	"net"
	//"os/user"
	//"maps"
	"math/rand/v2"
	"net/http"
	"net/http/httputil"
	"net/url"
	"os"
	"slices"
	"strconv"
	"strings"
	"time"
	//"runtime"
)

// MULTIPLEXER is a single object, "the_multiplexer".
type multiplexer struct {
	// EP_PORT is a listening port of Mux (":port").
	ep_port string
	manager *manager

	verbose bool

	table *keyval_table

	// MUX_EP and MUX_PID are about a process that a multiplexer and a
	// manager run in.
	mux_ep  string
	mux_pid int

	// MUX_ADDRS is a sorted list of ip adrresses.
	mux_addrs []string

	trusted_proxies []net.IP

	// CH_QUIT is to receive quitting notification.
	ch_quit_service <-chan vacuous

	server *http.Server

	conf *mux_conf
}

// THE_MULTIPLEXER is the single multiplexer instance.
var the_multiplexer = multiplexer{
	//pool: make(map[string]backend),
	//proc: make(map[int]backend),
}

const (
	empty_payload_hash_sha256 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
)

func configure_multiplexer(m *multiplexer, w *manager, t *keyval_table, q chan vacuous, c *mux_conf) {
	m.table = t
	m.manager = w
	m.conf = c
	m.ch_quit_service = q
	m.verbose = true
	//m.multiplexer_conf = conf.Multiplexer

	var conf = &m.conf.Multiplexer

	var host string
	if conf.Mux_node_name != "" {
		host = conf.Mux_node_name
	} else {
		var h, err1 = os.Hostname()
		if err1 != nil {
			panic(err1)
		}
		host = h
	}
	var port = conf.Port
	m.ep_port = net.JoinHostPort("", strconv.Itoa(port))
	m.mux_ep = net.JoinHostPort(host, strconv.Itoa(port))
	m.mux_pid = os.Getpid()

	conf.Forwarding_timeout = 60
	//m.client = &http.Client{}
	//m.proxy = m.client
	conf.Front_host = "localhost"

	var addrs []net.IP = convert_hosts_to_addrs(conf.Trusted_proxy_list)
	logger.debugf("Mux(%s) trusted_proxies=(%v)", m.mux_ep, addrs)
	if len(addrs) == 0 {
		panic("No trusted proxies")
	}
	m.trusted_proxies = addrs
}

// MEMO: ReverseProxy <: Handler as it implements ServeHTTP().
func start_multiplexer(m *multiplexer) {
	fmt.Println("start_multiplexer()")

	go mux_periodic_work(m)

	var proxy1 = httputil.ReverseProxy{
		Rewrite: proxy_request_rewriter(m),
	}
	var proxy2 = make_checker_proxy(m, &proxy1)
	m.server = &http.Server{
		Addr:    m.ep_port,
		Handler: proxy2,
	}

	logger.infof("Mux(%s) Start Mux", m.mux_ep)
	// var err2 = http.ListenAndServe(m.ep_port, proxy2)
	var err2 = m.server.ListenAndServe()
	logger.infof("Mux(%s) http.Server.ListenAndServe() done err=(%v)",
		m.mux_ep, err2)
}

// PROXY_REQUEST_REWRITER is a function in ReverseProxy.Rewriter.  It
// receives forwarding information from a forwarding-proxy via the
// http header "lens3-be".
func proxy_request_rewriter(m *multiplexer) func(r *httputil.ProxyRequest) {
	return func(r *httputil.ProxyRequest) {
		var x = r.In.Header["lens3-be"]
		//fmt.Printf("r.In.Header=%#v\n", r.In.Header)
		assert_fatal(len(x) == 2)
		var pool, ep = x[0], x[1]
		delete(r.In.Header, "lens3-be")
		delete(r.Out.Header, "lens3-be")

		// var be = get_backend(m.table, pool)
		// if be == nil {
		// 	logger.debug("Mux({pool}).")
		// 	raise(&proxy_exc{http_404_not_found, "pool non-exist"})
		// }

		fmt.Println("*** POOL=", pool, "to", "ep=", ep)
		//var g = m.pool[pool]
		//var proc = g.get_super_part()

		var url1, err1 = url.Parse("http://" + ep)
		if err1 != nil {
			logger.debugf("Mux(pool=%s) bad backend ep: ep=(%s) err=(%v)",
				pool, ep, err1)
			raise(&proxy_exc{http_500_internal_server_error,
				[][2]string{
					message_bad_backend_ep,
				}})
		}
		fmt.Println("*** URL=", url1)
		r.SetURL(url1)
		r.SetXForwarded()
	}
}

// MAKE_CHECKER_PROXY makes a filter that checks an access is granted.
// It passes the request to the next forwarding proxy.
func make_checker_proxy(m *multiplexer, proxy http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		defer handle_multiplexer_exc(m, w, r)
		fmt.Printf("*** r.Header.Get(Remote_Addr)=%#v\n", r.Header.Get("Remote_Addr"))
		fmt.Printf("*** r.RemoteAddr=%#v\n", r.RemoteAddr)

		if !ensure_frontend_proxy_trusted(m, w, r) {
			return
		}

		var authenticated, err1 = check_authenticated(m, r)
		if err1 != nil {
			return_mux_response_by_error(m, w, r, err1)
			return
		}
		var bucket, err2 = check_bucket_in_path(m, w, r)
		if err2 != nil {
			return_mux_response_by_error(m, w, r, err2)
			return
		}

		fmt.Println("*** secret=", authenticated.Access_key)

		switch {
		case authenticated != nil && authenticated.Secret_policy == secret_policy_internal_access:
			serve_internal_access(m, w, r, bucket, authenticated)
			return
		case bucket == nil && authenticated == nil:
			return_mux_response(m, w, r, http_400_bad_request,
				[][2]string{
					message_no_bucket_name,
				})
			return
		case bucket == nil && authenticated != nil:
			return_mux_response(m, w, r, http_403_forbidden,
				[][2]string{
					message_bucket_listing_forbidden,
				})
			return
		case bucket != nil && authenticated == nil:
			serve_anonymous_access(m, w, r, bucket, proxy)
			return
		case bucket != nil && authenticated != nil:
			serve_authenticated_access(m, w, r, bucket, authenticated, proxy)
			return
		default:
			panic_never()
		}
	})
}

func serve_authenticated_access(m *multiplexer, w http.ResponseWriter, r *http.Request, bucket *bucket_record, secret *secret_record, proxy http.Handler) {
	fmt.Println("*** AHO#2")
	assert_fatal(bucket != nil && secret != nil)
	var now int64 = time.Now().Unix()
	if !ensure_bucket_owner(m, w, r, bucket, secret) {
		return
	}
	if !ensure_bucket_not_expired(m, w, r, bucket, now) {
		return
	}
	fmt.Println("*** AHO#2-2")
	var pooldata *pool_record = ensure_pool_existence(m, w, r, bucket.Pool)
	if pooldata == nil {
		return
	}
	fmt.Println("*** AHO#2-3")
	if !ensure_user_is_active(m, w, r, pooldata.Owner_uid) {
		return
	}
	fmt.Println("*** AHO#2-4")
	//awake_suspended_pool()
	if !ensure_pool_state(m, w, r, pooldata.Pool) {
		return
	}
	if !ensure_permission_by_secret(m, w, r, secret) {
		return
	}
	fmt.Println("*** AHO#2-4")

	var be = ensure_backend_running(m, w, r, bucket.Pool)
	if be == nil {
		return
	}

	forward_access(m, w, r, be, proxy)
}

func serve_anonymous_access(m *multiplexer, w http.ResponseWriter, r *http.Request, bucket *bucket_record, proxy http.Handler) {
	fmt.Println("*** AHO#3")
	assert_fatal(bucket != nil)
	var now int64 = time.Now().Unix()
	if !ensure_bucket_not_expired(m, w, r, bucket, now) {
		return
	}
	var pooldata *pool_record = ensure_pool_existence(m, w, r, bucket.Pool)
	if pooldata == nil {
		return
	}
	if !ensure_user_is_active(m, w, r, pooldata.Owner_uid) {
		return
	}
	//awake_suspended_pool()
	if !ensure_pool_state(m, w, r, pooldata.Pool) {
		return
	}
	if !ensure_permission_by_bucket(m, w, r, bucket) {
		return
	}

	var be = ensure_backend_running(m, w, r, bucket.Pool)
	if be == nil {
		return
	}

	forward_access(m, w, r, be, proxy)
}

// FORWARD_ACCESS forwards a granted access to a backend.
func forward_access(m *multiplexer, w http.ResponseWriter, r *http.Request, be *backend_record, proxy http.Handler) {
	fmt.Println("*** AHO#4")

	// Start a backend.

	/*
		set_access_timestamp(m.table, pool)

		var be1 = get_backend(m.table, pool)
		if be1 == nil {
			var proc = start_backend(m.manager, pool)
			if proc == nil {
				return_mux_response(m, w, r, http_500_internal_server_error,
					[][2]string{
						message_cannot_start_backend,
					})
				return
			}
		}
		var be2 = get_backend(m.table, pool)
		if be2 == nil {
			return_mux_response(m, w, r, http_500_internal_server_error,
				[][2]string{
					message_backend_not_running,
				})
			return
		}

		fmt.Println("*** AHO#5")

		logger.debugf("Mux(pool=%s) backend=(%v)", pool, be2)
	*/

	// Replace an authorization header.

	sign_by_backend_credential(r, be)

	// Tell the endpoint to httputil.ReverseProxy.

	r.Header["lens3-be"] = []string{be.Pool, be.Backend_ep}
	proxy.ServeHTTP(w, r)
}

// SERVE_INTERNAL_ACCESS handles requests by probe_access_mux() from
// Registrar or other Multiplexers.  A call to
// make_absent_buckets_in_backend() has a race, but it results in only
// redundant work.
func serve_internal_access(m *multiplexer, w http.ResponseWriter, r *http.Request, bucket *bucket_record, secret *secret_record) {
	assert_fatal(secret != nil)
	logger.debugf("Mux(%s) internal-access: pool=(%s)",
		m.mux_ep, secret.Pool)

	// REJECT REQUESTS FROM THE OUTSIDE.

	//var peer = r.Header.Get("Remote_Addr")
	//var peer = r.RemoteAddr

	var pool = secret.Pool
	var pooldata *pool_record = ensure_pool_existence(m, w, r, pool)
	if pooldata == nil {
		return
	}
	if !ensure_user_is_active(m, w, r, pooldata.Owner_uid) {
		return
	}
	if !ensure_pool_state(m, w, r, pooldata.Pool) {
		return
	}

	var be = ensure_backend_running(m, w, r, secret.Pool)
	if be == nil {
		return
	}

	make_absent_buckets_in_backend(m.manager, be)
}

func handle_multiplexer_exc(m *multiplexer, w http.ResponseWriter, r *http.Request) {
	var x = recover()
	switch err1 := x.(type) {
	case nil:
	case *proxy_exc:
		fmt.Println("RECOVER!", err1)
		var msg = map[string]string{}
		for _, kv := range err1.message {
			msg[kv[0]] = kv[1]
		}
		var b1, err2 = json.Marshal(msg)
		assert_fatal(err2 == nil)
		http.Error(w, string(b1), err1.code)
	default:
		fmt.Println("TRAP unhandled panic", err1)
		fmt.Println("stacktrace:\n" + string(debug.Stack()))
		http.Error(w, "BAD", http_500_internal_server_error)
	}
}

// CHECK_AUTHENTICATED checks the signature in an AWS Authorization
// Header.  It returns a secret_record or nil.  It may return
// (nil,nil) when an authorization header is missing.
func check_authenticated(m *multiplexer, r *http.Request) (*secret_record, *proxy_exc) {
	var header = r.Header.Get("Authorization")
	var auth authorization_s3v4 = scan_aws_authorization(header)
	if auth.signature == "" {
		return nil, nil
	}
	var key string = auth.credential[0]
	var secret *secret_record = get_secret(m.table, key)
	if secret == nil {
		logger.infof("Mux(%s) unknown credential: access-key=(%s)",
			m.mux_ep, key)
		var err1 = &proxy_exc{
			http_401_unauthorized,
			[][2]string{
				message_unknown_credential,
			},
		}
		return nil, err1
	}
	assert_fatal(secret.Access_key == key)
	var keypair = [2]string{key, secret.Secret_key}
	var ok, reason = check_credential_in_request(r, keypair)
	if !ok {
		logger.infof("Mux(%s) bad credential, (%s): access-key=(%s)",
			m.mux_ep, reason, key)
		var err2 = &proxy_exc{
			http_401_unauthorized,
			[][2]string{
				message_bad_credential,
			},
		}
		return nil, err2
	}
	return secret, nil
}

// ENSURE_LENS3_IS_RUNNING checks if any Muxs are running.
func ensure_lens3_is_running__(t *keyval_table) bool {
	var muxs = list_mux_eps(t)
	return len(muxs) > 0
}

// ENSURE_BACKEND_RUNNING starts a backend if not running.  It updates
// a timestamp earlier before starting a backend.  It is to avoid a
// race in the start and stop of a backend.
func ensure_backend_running(m *multiplexer, w http.ResponseWriter, r *http.Request, pool string) *backend_record {
	set_access_timestamp(m.table, pool)

	var be1 = get_backend(m.table, pool)
	if be1 == nil {
		var proc = start_backend(m.manager, pool)
		if proc == nil {
			return_mux_response(m, w, r, http_500_internal_server_error,
				[][2]string{
					message_cannot_start_backend,
				})
			return nil
		}
	}

	var be2 = get_backend(m.table, pool)
	if be2 == nil {
		return_mux_response(m, w, r, http_500_internal_server_error,
			[][2]string{
				message_backend_not_running,
			})
		return nil
	}
	return be2
}

// ENSURE_POOL_EXISTENCE checks the pool exists.  It should never fail.
// It is inconsistent if a bucket exists but a pool does not.
func ensure_pool_existence(m *multiplexer, w http.ResponseWriter, r *http.Request, pool string) *pool_record {
	var pooldata *pool_record = get_pool(m.table, pool)
	if pooldata == nil {
		return_mux_response(m, w, r, http_404_not_found,
			[][2]string{
				message_nonexisting_pool,
			})
		return nil
	}
	return pooldata
}

func ensure_user_is_active(m *multiplexer, w http.ResponseWriter, r *http.Request, uid string) bool {
	var ok, reason = check_user_is_active(m.table, uid)
	if !ok {
		return_mux_response(m, w, r, http_401_unauthorized,
			[][2]string{
				reason,
			})
		return false
	}
	return true
}

// ENSURE_FORWARDING_HOST_TRUSTED checks the request sender is a
// frontend proxy or multiplexers.  It double checks m.mux_addrs,
// because mux_addrs is updated only when necessary.
func ensure_frontend_proxy_trusted(m *multiplexer, w http.ResponseWriter, r *http.Request) bool {
	//var peer = r.Header.Get("Remote_Addr")
	var peer = r.RemoteAddr
	if !check_frontend_proxy_trusted(m.trusted_proxies, peer) {
		logger.errf("Mux(%s) frontend proxy is untrusted: ep=(%v)",
			m.mux_ep, peer)
		return_mux_response(m, w, r, http_500_internal_server_error,
			[][2]string{
				message_Bad_proxy_configuration,
			})
		return false
	}
	return true
}

// CHECK_BUCKET_IN_PATH returns a bucket record for the name in the
// path.  It may return (nil,nil) if a bucket name is missing in the
// path.  It returns a proxy_exc as an error.
func check_bucket_in_path(m *multiplexer, w http.ResponseWriter, r *http.Request) (*bucket_record, *proxy_exc) {
	var bucketname, err1 = pick_bucket_in_path(m, r)
	if err1 != nil {
		return nil, err1
	}
	if bucketname == "" {
		return nil, nil
	}
	// assert_fatal(bucketname != "")
	var bucket = get_bucket(m.table, bucketname)
	if bucket == nil {
		var err2 = &proxy_exc{
			http_404_not_found,
			[][2]string{
				message_no_named_bucket,
			},
		}
		return nil, err2
	}
	return bucket, nil
}

func ensure_bucket_not_expired(m *multiplexer, w http.ResponseWriter, r *http.Request, bucket *bucket_record, now int64) bool {
	if bucket.Expiration_time < now {
		return_mux_response(m, w, r, http_400_bad_request,
			[][2]string{
				message_bucket_expired,
			})
		return false
	}
	return true
}

func ensure_bucket_owner(m *multiplexer, w http.ResponseWriter, r *http.Request, bucket *bucket_record, secret *secret_record) bool {
	if bucket.Pool != secret.Pool {
		return_mux_response(m, w, r, http_401_unauthorized,
			[][2]string{
				message_not_authorized,
			})
		return false
	}
	return true
}

func ensure_pool_state(m *multiplexer, w http.ResponseWriter, r *http.Request, pool string) bool {
	var reject_initial_state = false
	//AHOAHOAHO var state, _ = update_pool_state(t, pool, permitted)
	var state = pool_state_INITIAL //AHOAHOAHO
	switch state {
	case pool_state_INITIAL:
		if reject_initial_state {
			logger.errf("Mux(pool=%s) is in initial state.", pool)
			//raise(reg_error(403, "Pool is in initial state"))
			return_mux_response(m, w, r, http_500_internal_server_error,
				[][2]string{
					message_pool_not_ready,
				})
			return false
		}
	case pool_state_READY:
		// Skip.
	case pool_state_SUSPENDED:
		//raise(reg_error(503, "Pool suspended"))
		return_mux_response(m, w, r, http_503_service_unavailable,
			[][2]string{
				message_pool_suspended,
			})
		return false
	case pool_state_DISABLED:
		//raise(reg_error(403, "Pool disabled"))
		return_mux_response(m, w, r, http_403_forbidden,
			[][2]string{
				message_pool_disabled,
			})
		return false
	case pool_state_INOPERABLE:
		//raise(reg_error(403, "Pool inoperable"))
		return_mux_response(m, w, r, http_500_internal_server_error,
			[][2]string{
				message_pool_inoperable,
			})
		return false
	default:
		assert_fatal(false)
	}
	return true
}

func ensure_permission_by_secret(m *multiplexer, w http.ResponseWriter, r *http.Request, secret *secret_record) bool {
	var method string = r.Method
	var policy = secret.Secret_policy
	var set []secret_policy
	switch method {
	case "HEAD":
		fallthrough
	case "GET":
		set = []secret_policy{secret_policy_RW, secret_policy_RO}
	case "PUT":
		fallthrough
	case "POST":
		fallthrough
	case "DELETE":
		set = []secret_policy{secret_policy_RW, secret_policy_WO}
	default:
		logger.warnf("Mux(%s) http unknown method: method=(%s)",
			m.mux_ep, method)
		set = []secret_policy{}
	}
	var ok = slices.Contains(set, policy)
	if !ok {
		return_mux_response(m, w, r, http_403_forbidden,
			[][2]string{
				message_no_permission,
			})
		return false
	}
	return true
}

func ensure_permission_by_bucket(m *multiplexer, w http.ResponseWriter, r *http.Request, bucket *bucket_record) bool {
	var method string = r.Method
	var policy = bucket.Bucket_policy
	var set []bucket_policy
	switch method {
	case "HEAD":
		fallthrough
	case "GET":
		set = []bucket_policy{bucket_policy_RW, bucket_policy_RO}
	case "PUT":
		fallthrough
	case "POST":
		fallthrough
	case "DELETE":
		set = []bucket_policy{bucket_policy_RW, bucket_policy_WO}
	default:
		logger.warnf("Mux(%s) http unknown method: method=(%s)", m.mux_ep, method)
		set = []bucket_policy{}
	}
	var ok = slices.Contains(set, policy)
	if !ok {
		return_mux_response(m, w, r, http_403_forbidden,
			[][2]string{
				message_no_permission,
			})
		return false
	}
	return true
}

// PICK_BUCKET_IN_PATH returns a bucket name in a request or "" when a
// bucket name is missing.  It may return an error.
func pick_bucket_in_path(m *multiplexer, r *http.Request) (string, *proxy_exc) {
	var u1 = r.URL
	var path = strings.Split(u1.EscapedPath(), "/")
	if len(path) >= 2 && path[0] != "" {
		return "", nil
	}
	var bucket = path[1]
	if bucket == "" {
		return "", nil
	}
	if !check_bucket_naming(bucket) {
		var err1 = &proxy_exc{
			http_400_bad_request,
			[][2]string{
				message_bad_bucket_name,
			},
		}
		return bucket, err1
	}
	return bucket, nil
}

func return_mux_response(m *multiplexer, w http.ResponseWriter, r *http.Request, code int, message [][2]string) {
	var msg = map[string]string{}
	for _, kv := range message {
		msg[kv[0]] = kv[1]
	}
	var rspn = &error_response{
		response_common: response_common{
			Status:    "error",
			Reason:    msg,
			Timestamp: time.Now().Unix(),
		},
	}
	var b1, err1 = json.Marshal(rspn)
	assert_fatal(err1 == nil)
	http.Error(w, string(b1), code)
	log_access(r, code)
}

func return_mux_response_by_error(m *multiplexer, w http.ResponseWriter, r *http.Request, err error) {
	switch err2 := err.(type) {
	case *proxy_exc:
		return_mux_response(m, w, r, err2.code, err2.message)
	default:
		logger.errf("Mux(%s) (interanl) unexpected error: err=(%v)",
			m.mux_ep, err)
		raise(err)
	}
}

func mux_periodic_work(m *multiplexer) {
	var conf = &m.conf.Multiplexer
	logger.debugf("Mux(%s) Periodic work started", m.mux_ep)

	var now int64 = time.Now().Unix()
	var mux = &mux_record{
		Mux_ep:     m.mux_ep,
		Start_time: now,
		Timestamp:  now,
	}

	var interval = int64(conf.Mux_ep_update_interval)
	var expiry int64 = 3 * interval
	assert_fatal(interval >= 10)
	//time.Sleep(1 * time.Second)
	for {
		if m.verbose {
			logger.debugf("Mux(%s) Update Mux-ep", m.mux_ep)
		}
		mux.Timestamp = time.Now().Unix()
		set_mux_ep(m.table, m.mux_ep, mux)
		var ok = set_mux_ep_expiry(m.table, m.mux_ep, expiry)
		if !ok {
			// Ignore an error.
			logger.errf("Mux() Bad call set_mux_ep_expiry()")
		}
		var jitter = rand.Int64N(interval / 8)
		time.Sleep(time.Duration(interval+jitter) * time.Second)
	}
}
