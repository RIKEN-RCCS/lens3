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
	//"io"
	"encoding/json"
	"log"
	//"os"
	"net"
	"os/user"
	//"maps"
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

// MULTIPLEXER is a single object, "the_multiplexer".  It is
// with threads of a child process reaper.
type multiplexer struct {
	// EP is a listening port of Mux.
	ep string

	verbose bool

	table *keyval_table

	// MUX_EP and MUX_PID are about a process that a multiplexer and a
	// manager run in.
	mux_ep  string
	mux_pid int

	// BE factory is to make a backend.
	//be backend_factory

	// POOL maps a POOL-ID to a process record.
	//pool map[string]backend

	// PROC maps a PID to a process record.  PID is int in "os".
	//proc map[int]backend

	// CH_SIG is a channel to receive SIGCHLD.
	//ch_sig chan os.Signal

	// CLIENT accesses backend servers.
	// client http.Client

	//proxy *backend_proxy

	// MUX_ADDRS is a sorted list of ip adrresses.
	mux_addrs []string
	// mux_addrs = m.list_mux_ip_addresses()

	// UNKNOW FIELDS OF Multiplexer_conf.
	// front_host_ip?
	// periodic_work_interval?
	// mux_expiry?

	trusted_proxies []net.IP

	conf *mux_conf
	//multiplexer_conf
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

var (
	message_backend_not_running = [2]string{
		"message", "Backend not running"}

	message_bad_signature = [2]string{
		"message", "Bad signature"}
	message_not_authenticated = [2]string{
		"message", "Not authenticated"}

	message_no_bucket_name = [2]string{
		"message", "No bucket name"}
	message_bad_bucket_name = [2]string{
		"message", "Bad bucket name"}
	message_no_named_bucket = [2]string{
		"message", "No named bucket"}

	message_bucket_expired = [2]string{
		"message", "Bucket expired"}

	message_bucket_listing_forbidden = [2]string{
		"message", "Bucket listing forbidden"}

	message_bad_pool = [2]string{
		"message", "Bad pool"}
)

func configure_multiplexer(m *multiplexer, t *keyval_table, c *mux_conf) {
	m.table = t
	m.conf = c
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
	m.ep = net.JoinHostPort("", strconv.Itoa(port))
	m.mux_ep = net.JoinHostPort(host, strconv.Itoa(port))
	m.mux_pid = os.Getpid()

	conf.Forwarding_timeout = 60
	//m.client = &http.Client{}
	//m.proxy = m.client
	conf.Front_host = "localhost"

	var addrs []net.IP = convert_hosts_to_addrs(conf.Trusted_proxy_list)
	logger.debugf("Mux(%s) trusted_proxies=(%v)", m.ep, addrs)
	if len(addrs) == 0 {
		panic("No trusted proxies")
	}
	m.trusted_proxies = addrs
}

func start_multiplexer(m *multiplexer) {
	fmt.Println("start_multiplexer()")

	// MEMO: ReverseProxy <: Handler as it implements ServeHTTP().

	var proxy1 = httputil.ReverseProxy{
		Rewrite: proxy_request_rewriter(m),
	}
	var proxy2 = make_forwarding_proxy(m, &proxy1)
	var proxy3 = make_checker_proxy(m, proxy2)

	logger.infof("Mux(%s) start service", m.ep)
	for {
		var err2 = http.ListenAndServe(m.ep, proxy3)
		logger.infof("Mux(%s) ListenAndServe() done err=%v", m.ep, err2)
		log.Fatal(err2)
	}
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
			raise(&proxy_exc{http_404_not_found, "pool non-exist"})
		}
		fmt.Println("*** POOL=", pool, " BE=", be)
		//var g = m.pool[pool]
		//var proc = g.get_super_part()
		var url1, err1 = url.Parse("http://" + be.Backend_ep)
		if err1 != nil {
			logger.debugf("Mux(pool=%s) bad backend url: err=(%v)", pool, err1)
			raise(&proxy_exc{http_500_internal_server_error,
				"bad url"})
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

		//var g = m.pool["mMwfyMzLwOlb8QLYANRM"]
		//var proc = g.get_super_part()
		//var proc = get_backend_process(m.table, "mMwfyMzLwOlb8QLYANRM")
		//fmt.Println("*** POOL=", pool)

		if !ensure_frontend_proxy_trusted(m, w, r) {
			return
		}

		// A bucket-name can be "".

		var bucket = ensure_bucket_in_path(m, w, r)
		var authenticated = check_authenticated(m, r)

		switch {
		case bucket == nil && authenticated == nil:
			return_mux_error_response(m, w, r, http_400_bad_request,
				[][2]string{
					message_no_bucket_name,
				})
			return
		case bucket == nil && authenticated != nil:
			return_mux_error_response(m, w, r, http_403_forbidden,
				[][2]string{
					message_bucket_listing_forbidden,
				})
			return
		case bucket != nil && authenticated == nil:
			serve_authenticated_access(m, w, r, bucket, authenticated, proxy)
		case bucket != nil && authenticated != nil:
			serve_anonymous_access(m, w, r, bucket, proxy)
		default:
			panic("(intenal(")
		}

		var now int64 = time.Now().Unix()
		if !ensure_bucket_not_expired(m, w, r, bucket, now) {
			return
		}

		if !ensure_bucket_policy(m, w, r, bucket, authenticated) {
			return
		}

		proxy.ServeHTTP(w, r)
	})
}

// MAKE_FORWARDING_PROXY makes a filter that signs the request with a
// backend credential and passes it to the next handler proxy.  It
// passes information to the next handler via an http header
// "lens3-pool".  See proxy_request_rewriter().
func make_forwarding_proxy(m *multiplexer, proxy http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		var pool = "d4f0c4645fce5734"
		//var pool = generate_random_key()
		var desc = get_backend_process(m.table, pool)
		logger.debugf("Mux(pool=%s) backend=%v.", pool, desc)
		if desc == nil {
			http.Error(w, "BAD", http_500_internal_server_error)
			raise(&proxy_exc{http_500_internal_server_error,
				"backend_not_running"})
		}

		var uid = "AHOAHOAHO"

		//http.Error(w, "ERROR!", http.StatusMethodNotAllowed)
		ensure_pool_state(m.table, pool)
		ensure_user_is_active(m.table, uid)
		ensure_secret_owner(m, r)
		//logger.error(("Mux ({m._mux_host}) Got a request from" +
		//	" untrusted proxy or unknonwn Mux: {peer_addr};" +
		//	" Check configuration"))

		/* Replace an authorization header. */

		sign_by_backend_credential(r, desc)

		r.Header["lens3-pool"] = []string{pool}
		proxy.ServeHTTP(w, r)
	})
}

func serve_authenticated_access(m *multiplexer, w http.ResponseWriter, r *http.Request, bucket *bucket_record, secret *secret_record, proxy http.Handler) {
	assert_fatal(bucket != nil && secret != nil)

	if !ensure_bucket_owner(m, w, r, bucket, secret) {
		return
	}

	if !check_permission_by_secret(m, w, r, secret) {
		return
	}

	var prop *pool_record = get_pool(m.table, bucket.Pool)
	if prop == nil {
		return_mux_error_response(m, w, r, http_404_not_found,
			[][2]string{
				message_bad_pool,
			})
		return
	}
	if !ensure_user_is_active(m.table, prop.Owner_uid) {
		return
	}
	if !ensure_pool_state(m.table, prop.Pool) {
		return
	}

	proxy.ServeHTTP(w, r)
}

func serve_anonymous_access(m *multiplexer, w http.ResponseWriter, r *http.Request, bucket *bucket_record, proxy http.Handler) {
	proxy.ServeHTTP(w, r)
}

// CHECK_AUTHENTICATED checks the signature in an AWS Authorization
// Header.  It returns a secret_record or nil.
func check_authenticated(m *multiplexer, r *http.Request) *secret_record {
	var header = r.Header.Get("Authorization")
	var a2 authorization_s3v4 = scan_aws_authorization(header)
	if a2.signature == "" {
		return nil
	}
	var key string = a2.credential[0]
	var secret *secret_record = get_secret(m.table, key)
	if secret == nil {
		return nil
	}
	assert_fatal(secret._access_key == key)
	var keypair = [2]string{key, secret.Secret_key}
	var ok = check_credential_in_request(m.verbose, r, keypair)
	if !ok {
		return nil
	}
	return secret
}

// (ensure_mux_is_running) ENSURE_LENS3_IS_RUNNING checks if any Muxs
// are running.
func ensure_lens3_is_running(t *keyval_table) bool {
	var muxs = list_mux_eps(t)
	return len(muxs) > 0
}

func check_permission_by_secret(m *multiplexer, w http.ResponseWriter, r *http.Request, secret *secret_record) bool {
	var method string = r.Method
	var policy = secret.Secret_policy
	var policyset []secret_policy
	switch method {
	case "GET":
		policyset = []secret_policy{secret_policy_RW, secret_policy_RO}
	case "PUT":
		policyset = []secret_policy{secret_policy_RW, secret_policy_WO}
	case "POST":
		policyset = []secret_policy{secret_policy_RW, secret_policy_WO}
	default:
		logger.warnf("Mux(%s) http unknown method: method=(%s)", m.ep, method)
		policyset = []secret_policy{}
	}
	return slices.Contains(policyset, policy)
}

func check_permission_by_bucket(m *multiplexer, w http.ResponseWriter, r *http.Request, bucket *bucket_record) bool {
	var method string = r.Method
	var policy = bucket.Bucket_policy
	var set []bucket_policy
	switch method {
	case "GET":
		set = []bucket_policy{bucket_policy_PUBLIC, bucket_policy_DOWNLOAD}
	case "PUT":
		set = []bucket_policy{bucket_policy_PUBLIC, bucket_policy_UPLOAD}
	case "POST":
		set = []bucket_policy{bucket_policy_PUBLIC, bucket_policy_UPLOAD}
	default:
		logger.warnf("Mux(%s) http unknown method: method=(%s)", m.ep, method)
		set = []bucket_policy{}
	}
	return slices.Contains(set, policy)
}

func ensure_user_is_active(t *keyval_table, uid string) bool {
	var ui = get_user(t, uid)
	var now int64 = time.Now().Unix()
	if ui != nil {
		return false
	}
	if !ui.Enabled || ui.Expiration_time < now {
		return false
	}

	var _, err1 = user.Lookup(uid)
	if err1 != nil {
		switch err1.(type) {
		case user.UnknownUserError:
		default:
		}
		logger.warnf("user.Lookup(%s) fails: err=(%v)", uid, err1)
		return false
	}
	// (uu.Uid : string, uu.Gid : string)

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
			m.ep, peer)
		return_mux_error_response(m, w, r, http_500_internal_server_error,
			[][2]string{
				message_Bad_proxy_configuration,
			})
		return false
	}
	return true
}

func ensure_bucket_in_path(m *multiplexer, w http.ResponseWriter, r *http.Request) *bucket_record {
	var bucketname, err1 = pick_bucket_in_path(m, r)
	if err1 != nil {
		switch e1 := err1.(type) {
		case *proxy_exc:
			return_mux_error_response(m, w, r, e1.code,
				[][2]string{
					{"message", e1.message},
				})
			return nil
		default:
			raise(err1)
		}
	}
	if bucketname != "" {
		var bucket = get_bucket(m.table, bucketname)
		if bucket == nil {
			return_mux_error_response(m, w, r, http_404_not_found,
				[][2]string{
					message_no_named_bucket,
				})
			return nil
		}
		return bucket
	} else {
		return nil
	}
}

func ensure_bucket_not_expired(m *multiplexer, w http.ResponseWriter, r *http.Request, bucket *bucket_record, now int64) bool {
	if bucket.Expiration_time < now {
		return_mux_error_response(m, w, r, http_400_bad_request,
			[][2]string{
				message_bucket_expired,
			})
		return false
	}
	return true
}

// ENSURE_BUCKET_POLICY performs a weak check that a bucket accepts
// any public access or an access has an access-key.
func ensure_bucket_policy(m *multiplexer, w http.ResponseWriter, r *http.Request, bucket *bucket_record, secret *secret_record) bool {
	if bucket.Bucket_policy != bucket_policy_NONE && secret == nil {
		return true
	} else {
		return_mux_error_response(m, w, r, http_401_unauthorized,
			[][2]string{
				message_not_authenticated,
			})
		return false
	}
}

func ensure_bucket_owner(m *multiplexer, w http.ResponseWriter, r *http.Request, bucket *bucket_record, secret *secret_record) bool {
	if bucket.Pool != secret.Pool {
		return_mux_error_response(m, w, r, http_401_unauthorized,
			[][2]string{
				message_not_authenticated,
			})
		return false
	}
	return true
}

func ensure_secret_owner(m *multiplexer, r *http.Request) bool {
	/*
		    u = tables.get_user(user_id)
		    assert u is not None
		    if not u.get("enabled") {
		        raise Reg_Error(403, (f"User disabled: {user_id}"))
			}
	*/
	return true
}

func ensure_pool_state(t *keyval_table, pool string) bool {
	var reject_initial_state = false
	//AHOAHOAHO var state, _ = update_pool_state(t, pool, permitted)
	var state = pool_state_INITIAL //AHOAHOAHO
	switch state {
	case pool_state_INITIAL:
		if reject_initial_state {
			logger.errf("Mux(pool=%s) is in initial state.", pool)
			raise(reg_error(403, "Pool is in initial state"))
		}
	case pool_state_READY:
		// Skip.
	case pool_state_SUSPENDED:
		raise(reg_error(503, "Pool suspended"))
	case pool_state_DISABLED:
		raise(reg_error(403, "Pool disabled"))
	case pool_state_INOPERABLE:
		raise(reg_error(403, "Pool inoperable"))
	default:
		assert_fatal(false)
	}
	return true
}

func return_mux_error_response(m *multiplexer, w http.ResponseWriter, r *http.Request, code int, reason [][2]string) {
	var msg = map[string]string{}
	for _, kv := range reason {
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
	log_access(code, r)
}

// PICK_BUCKET_IN_PATH returns a bucket name in a request or "" when a
// bucket part is missing.  It may return an error.
func pick_bucket_in_path(m *multiplexer, r *http.Request) (string, error) {
	var u1 = r.URL
	var path = strings.Split(u1.EscapedPath(), "/")
	if len(path) >= 2 && path[0] != "" {
		return "", nil
		//raise(&proxy_exc{http_400_bad_request,
		//no_bucket_name_in_url})
	}
	var bucket = path[1]
	if bucket == "" {
		return "", nil
	}
	if !check_bucket_naming(bucket) {
		var err = &proxy_exc{
			http_400_bad_request,
			message_bad_bucket_name[1],
		}
		return bucket, err
	}
	return bucket, nil
}
