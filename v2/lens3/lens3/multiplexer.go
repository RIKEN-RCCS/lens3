/* Lens3-Multiplexer.  Main part of Lens3. */

// Copyright 2022-2024 RIKEN R-CCS.
// SPDX-License-Identifier: BSD-2-Clause

package lens3

// Multiplexer is a proxy to backend S3 servers.

// NOTE: Do not call panic(http/ErrAbortHandler) to abort processing
// in httputil/ReverseProxy.ErrorHandler.  Aborting does not send a
// response but closes a connection.

// MEMO: A request can be obtained from the http/Response argument (as
// .Request) to a function httputil/ReverseProxy.ModifyResponse,
// although it is a server-side response and the document says: "This
// is only populated for Client requests."

// MEMO: http/HandlerFunc is a function type.  It is
// (ResponseWriter,Request)→unit

// MEMO: httputil/ReverseProxy <: Handler as it implements
// ServeHTTP().

import (
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"math/rand/v2"
	"net"
	"net/http"
	"net/http/httputil"
	"net/url"
	"os"
	"os/user"
	"runtime"
	"runtime/debug"
	"slices"
	"strconv"
	"strings"
	"sync"
	"time"
)

// MULTIPLEXER is a single object, "the_multiplexer".  EP_PORT is a
// listening port of a Multiplexer (it is ":port").  MUX_EP and
// MUX_PID are about a process that a Multiplexer and a Manager run
// in.  LOGPREFIX≡"Mux: " is a printing name of this Multiplexer.
// CH_QUIT_SERVICE is to receive quitting notification.
type multiplexer struct {
	ep_port string

	manager *manager

	mux_ep  string
	mux_pid int

	table *keyval_table

	trusted_proxies []net.IP

	logprefix string

	ch_quit_service <-chan vacuous

	server *http.Server

	conf *mux_conf
}

// THE_MULTIPLEXER is the single Multiplexer instance.
var the_multiplexer = &multiplexer{}

func configure_multiplexer(m *multiplexer, w *manager, t *keyval_table, qch <-chan vacuous, c *mux_conf) {
	m.table = t
	m.manager = w
	m.conf = c
	m.ch_quit_service = qch

	var conf = &m.conf.Multiplexer
	open_log_for_mux(c.Log.Access_log_file)

	var host string
	if conf.Mux_node_name != "" {
		host = conf.Mux_node_name
	} else {
		var h, err1 = os.Hostname()
		if err1 != nil {
			slogger.Error(m.logprefix+"os/Hostname() errs", "err", err1)
			panic(nil)
		}
		host = h
	}
	var port = conf.Port
	m.ep_port = net.JoinHostPort("", strconv.Itoa(port))
	m.mux_ep = net.JoinHostPort(host, strconv.Itoa(port))
	m.mux_pid = os.Getpid()
	m.logprefix = ITE(false, fmt.Sprintf("Mux(%s): ", m.mux_ep), "Mux: ")

	var addrs []net.IP = convert_hosts_to_addrs(conf.Trusted_proxy_list)
	slogger.Debug(m.logprefix+"Trusted proxies", "ip", addrs)
	if len(addrs) == 0 {
		slogger.Error(m.logprefix + "No trusted proxies")
		panic(nil)
	}
	m.trusted_proxies = addrs
}

func start_multiplexer(m *multiplexer, wg *sync.WaitGroup) {
	defer func() {
		var x = recover()
		if x != nil {
			slogger.Error("Mux: Multiplexer main errs", "err", x,
				"stack", string(debug.Stack()))
		}
	}()
	defer wg.Done()
	defer force_quit_service()

	if trace_task&tracing != 0 {
		slogger.Debug(m.logprefix + "start_multiplexer()")
	}

	go mux_periodic_work(m)

	var loglogger = slog.NewLogLogger(slogger.Handler(), slog.LevelDebug)
	var proxy1 = httputil.ReverseProxy{
		Rewrite:        proxy_request_rewriter(m),
		ModifyResponse: proxy_access_addenda(m),
		ErrorLog:       loglogger,
		ErrorHandler:   proxy_error_handler(m),
	}
	var proxy2 = make_checker_proxy(m, &proxy1)
	m.server = &http.Server{
		Addr:     m.ep_port,
		Handler:  proxy2,
		ErrorLog: loglogger,
		//BaseContext: func(net.Listener) context.Context,
	}

	go func() {
		select {
		case <-m.ch_quit_service:
			var ctx = context.Background()
			m.server.Shutdown(ctx)
		}
	}()

	slogger.Info(m.logprefix+"Start Multiplexer", "ep", m.mux_ep)
	var err1 = m.server.ListenAndServe()
	slogger.Error(m.logprefix+"http/Server.ListenAndServe() EXITS",
		"ep", m.mux_ep, "err", err1)
}

// MUX_PERIODIC_WORK keeps registering the endpoint of Multiplexer in
// the keyval-db.
func mux_periodic_work(m *multiplexer) {
	defer func() {
		var x = recover()
		if x != nil {
			slogger.Error(m.logprefix+"Mux periodic work errs", "err", x,
				"stack", string(debug.Stack()))
		}
	}()

	var conf = &m.conf.Multiplexer
	if trace_task&tracing != 0 {
		slogger.Debug(m.logprefix + "Mux periodic work started")
	}
	var now int64 = time.Now().Unix()
	var mux = &mux_record{
		Mux_ep:     m.mux_ep,
		Start_time: now,
		Timestamp:  now,
	}

	var interval = (conf.Mux_ep_update_interval).time_duration()
	var expiry = 2 * interval
	assert_fatal(interval >= (10 * time.Second))
	for {
		if trace_task&tracing != 0 {
			slogger.Debug(m.logprefix + "Update Mux-ep")
		}
		mux.Timestamp = time.Now().Unix()
		set_mux_ep(m.table, m.mux_ep, mux)
		var ok = set_mux_ep_expiry(m.table, m.mux_ep, expiry)
		if !ok {
			// Ignore an error.
			slogger.Error(m.logprefix+"DB.Expire(mux-ep) failed",
				"mux-ep", m.mux_ep)
		}
		var jitter = time.Duration(rand.Int64N(int64(interval) / 10))
		time.Sleep(interval + jitter)
	}
}

// PROXY_REQUEST_REWRITER makes a function for ReverseProxy.Rewriter.
// It receives a forwarding url via the context value "lens3-be".
func proxy_request_rewriter(m *multiplexer) func(*httputil.ProxyRequest) {
	return func(r *httputil.ProxyRequest) {
		var ctx = r.In.Context()
		var x1 = ctx.Value("lens3-be")
		var forwarding, ok = x1.(*url.URL)
		assert_fatal(ok)
		r.SetURL(forwarding)
		if false {
			r.SetXForwarded()
		}

		if trace_proxy&tracing != 0 {
			slogger.Debug(m.logprefix+"Forward request",
				"url", forwarding)
		}
	}
}

// PROXY_ACCESS_ADDENDA makes a callback that is called at returning a
// response by httputil/ReverseProxy.  It is to generate an access
// log.
func proxy_access_addenda(m *multiplexer) func(*http.Response) error {
	return func(rspn *http.Response) error {
		if rspn.StatusCode != 200 {
			delay_sleep(m.conf.Multiplexer.Error_response_delay_ms)
		}
		var ctx = rspn.Request.Context()
		var x = ctx.Value("lens3-pool-auth")
		var poolauth, ok = x.([]string)
		var auth = ""
		if ok {
			auth = poolauth[1]
		}
		log_mux_access_by_response(rspn, auth)
		return nil
	}
}

// PROXY_ERROR_HANDLER makes an "ErrorHandler" for
// httputil/ReverseProxy that returns a response.  Errors in proxying
// are considered temporary and it returns HTTP status 503.  It is
// because backends refuse connections when they are busy.
func proxy_error_handler(m *multiplexer) func(http.ResponseWriter, *http.Request, error) {
	return func(w http.ResponseWriter, rqst *http.Request, err error) {
		var ctx = rqst.Context()
		var x = ctx.Value("lens3-pool-auth")
		var poolauth, ok = x.([]string)
		var pool = ""
		var auth = ""
		if ok {
			pool = poolauth[0]
			auth = poolauth[1]
		}
		slogger.Error((m.logprefix + "httputil/ReverseProxy() failed"),
			"pool", pool, "key", auth, "err", err, "requst", rqst)

		var err1 = &proxy_exc{
			auth,
			"",
			http_503_service_unavailable,
			message_503_proxying_failed,
			nil,
		}
		return_mux_error_response(m, w, rqst, err1)

		//panic(http.ErrAbortHandler)
	}
}

// MAKE_CHECKER_PROXY makes a filter that checks an access is granted.
// It passes the request to the next forwarding proxy.
func make_checker_proxy(m *multiplexer, proxy http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		defer handle_multiplexer_exc(m, w, r)
		if trace_proxy&tracing != 0 {
			slogger.Debug(m.logprefix+"Check request",
				"method", r.Method, "resource", r.RequestURI)
		}

		//fmt.Printf("*** r.Remote_Addr=%#v\n", r.Header.Get("Remote_Addr"))
		//fmt.Printf("*** r.RemoteAddr=%#v\n", r.RemoteAddr)

		if !ensure_frontend_proxy_trusted(m, w, r) {
			return
		}

		var authenticated, err1 = check_authenticated(m, r)
		if err1 != nil {
			// (An error is already logged).
			return_mux_error_response(m, w, r, err1)
			return
		}
		var auth string = ""
		if authenticated != nil {
			auth = authenticated.Access_key
		}

		var bucket, err2 = check_bucket_in_path(m, w, r, auth)
		if err2 != nil {
			// (An error is already logged).
			return_mux_error_response(m, w, r, err2)
			return
		}

		var probing = (authenticated != nil &&
			authenticated.Secret_policy == secret_policy_internal_access)
		switch {
		case probing:
			serve_probe_access(m, w, r, bucket, authenticated)
			return
		case bucket == nil && authenticated == nil:
			// Lens3 disallows bucket listing.
			slogger.Info(m.logprefix+"Bad bucket naming", "bucket", "/")
			var err4 = &proxy_exc{
				auth,
				"",
				http_403_forbidden,
				message_40x_access_rejected,
				nil,
			}
			return_mux_error_response(m, w, r, err4)
			return
		case bucket == nil && authenticated != nil:
			slogger.Debug(m.logprefix+"Reject access at the top",
				"key", auth)
			var err5 = &proxy_exc{
				auth,
				"",
				http_400_bad_request,
				message_400_bucket_listing_forbidden,
				nil,
			}
			return_mux_error_response(m, w, r, err5)
			return
		case bucket != nil && authenticated == nil:
			// THIS CAN BE PORT SCANS.
			serve_anonymous_access(m, w, r, bucket, proxy)
			return
		case bucket != nil && authenticated != nil:
			serve_authenticated_access(m, w, r, bucket, authenticated, proxy)
			return
		default:
			panic(nil)
		}
	})
}

func serve_authenticated_access(m *multiplexer, w http.ResponseWriter, r *http.Request, bucket *bucket_record, secret *secret_record, proxy http.Handler) {
	assert_fatal(bucket != nil && secret != nil)
	var auth = ""
	if secret != nil {
		auth = secret.Access_key
	}
	if !ensure_bucket_owner(m, w, r, bucket, secret, auth) {
		return
	}

	if !ensure_bucket_not_expired(m, w, r, bucket, auth) {
		return
	}
	var pool = bucket.Pool
	var pooldata *pool_record = ensure_pool_existence(m, w, r, pool, auth)
	if pooldata == nil {
		return
	}
	if !ensure_pool_state(m, w, r, pooldata, auth) {
		return
	}
	if !ensure_permission_by_secret(m, w, r, secret, auth) {
		return
	}

	var be = ensure_backend_running(m, w, r, bucket.Pool, auth)
	if be == nil {
		return
	}

	forward_access(m, w, r, be, secret.Access_key, proxy)
}

func serve_anonymous_access(m *multiplexer, w http.ResponseWriter, r *http.Request, bucket *bucket_record, proxy http.Handler) {
	assert_fatal(bucket != nil)
	var auth = ""
	if !ensure_bucket_not_expired(m, w, r, bucket, auth) {
		return
	}
	var pool = bucket.Pool
	var pooldata *pool_record = ensure_pool_existence(m, w, r, pool, auth)
	if pooldata == nil {
		return
	}
	if !ensure_pool_state(m, w, r, pooldata, auth) {
		return
	}
	if !ensure_permission_by_bucket(m, w, r, bucket, auth) {
		return
	}

	var be = ensure_backend_running(m, w, r, bucket.Pool, auth)
	if be == nil {
		return
	}

	forward_access(m, w, r, be, "", proxy)
}

// FORWARD_ACCESS forwards a granted access to a backend.
func forward_access(m *multiplexer, w http.ResponseWriter, r *http.Request, be *backend_record, auth string, proxy http.Handler) {
	// Replace an authorization header.

	var err1 = sign_by_backend_credential(r, be)
	if err1 != nil {
		slogger.Error(m.logprefix+"aws.signer/SignHTTP() errs", "err", err1)
		raise(&proxy_exc{
			auth,
			"",
			http_500_internal_server_error,
			message_500_sign_failed,
			nil,
		})
	}

	// Tell the forwarding endpoint to httputil/ReverseProxy.

	var pool = be.Pool
	var ep = be.Backend_ep
	var forwarding, err2 = url.Parse("http://" + ep)
	if err2 != nil {
		slogger.Error(m.logprefix+"Bad backend ep", "ep", ep, "err", err2)
		raise(&proxy_exc{
			auth,
			"",
			http_500_internal_server_error,
			message_50x_internal_error,
			nil,
		})
	}
	var ctx1 = r.Context()
	var ctx2 = context.WithValue(ctx1, "lens3-be", forwarding)
	var ctx3 = context.WithValue(ctx2, "lens3-pool-auth", []string{pool, auth})
	var r2 = r.WithContext(ctx3)

	slogger.Info(m.logprefix+"Forward request",
		"pool", pool, "key", auth,
		"method", r2.Method, "resource", r2.RequestURI)
	if trace_proxy&tracing != 0 {
		slogger.Debug(m.logprefix+"Forward request",
			"pool", pool, "key", auth,
			"request", r2)
	}

	proxy.ServeHTTP(w, r2)
}

// SERVE_PROBE_ACCESS handles requests by probe_access_mux() from
// Registrar.  It tries to make buckets in the backend.  It rejects
// requests from the outside (ie, thru a proxy).  Calling
// make_absent_buckets_in_backend() is not mutexed.  A critical case
// is that an error cancels a work to make a bucket in Registrar, but
// the error is for another bucket.  It returns http 502 on an error,
// as clients retry for http 500.
func serve_probe_access(m *multiplexer, w http.ResponseWriter, r *http.Request, bucket *bucket_record, secret *secret_record) {
	assert_fatal(secret != nil)
	var auth = secret.Access_key
	var pool = secret.Pool
	slogger.Debug(m.logprefix+"Serve probe-access", "pool", pool)

	var peer = r.Header.Get("Remote_Addr")
	if peer != "" {
		slogger.Error(m.logprefix+"Probe-access from outside",
			"remote", peer)
		var err1 = &proxy_exc{
			auth,
			"",
			http_500_internal_server_error,
			message_500_access_rejected,
			nil,
		}
		return_mux_error_response(m, w, r, err1)
		return
	}

	var pooldata *pool_record = ensure_pool_existence(m, w, r, pool, auth)
	if pooldata == nil {
		return
	}
	if !ensure_pool_state(m, w, r, pooldata, auth) {
		return
	}

	var be = ensure_backend_running(m, w, r, pool, auth)
	if be == nil {
		return
	}

	var err2 = make_absent_buckets_in_backend(m.manager, be)
	if err2 != nil {
		// (An error is already logged).
		var message = prettify_error_message(err2.Error())
		var err3 = &proxy_exc{
			auth,
			"",
			http_502_bad_gateway,
			message_502_bucket_creation_failed,
			map[string]string{
				"err": message,
			},
		}
		return_mux_error_response_no_delay(m, w, r, err3)
		return
	}

	return_success_response_for_probe(m, w, r, auth)
}

// PRETTIFY_ERROR_MESSAGE removes garbages in an error message, such
// as ":_" followed by nothing.  It is intended for
// "BucketAlreadyOwnedByYou: ".
func prettify_error_message(m string) string {
	var m2 = strings.TrimSpace(m)
	var m3 string
	if strings.HasSuffix(m2, ":") {
		m3 = m2[:len(m2)-1]
	} else {
		m3 = m2
	}
	return m3
}

type access_logger = func(rqst *http.Request, code int, length int64, uid string, auth string)

// HANDLE_MULTIPLEXER_EXC should be called by defer, directly.
func handle_multiplexer_exc(m *multiplexer, w http.ResponseWriter, rqst *http.Request) {
	var x = recover()
	var delay_ms = m.conf.Multiplexer.Error_response_delay_ms
	var logprefix = m.logprefix
	var logfn = log_mux_access_by_request
	handle_exc(x, w, rqst, delay_ms, logprefix, logfn)
}

func handle_exc(x any, w http.ResponseWriter, rqst *http.Request, delay_ms time_in_ms, logprefix string, logfn access_logger) {
	switch err1 := x.(type) {
	case nil:
		// Okay.
	case *runtime.PanicNilError:
		slogger.Error(logprefix+"FATAL ERROR", "err", err1,
			"stack", string(debug.Stack()))

		var err2 = &proxy_exc{
			"",
			"",
			http_500_internal_server_error,
			message_50x_internal_error,
			nil,
		}
		return_error_response(w, rqst, err2, delay_ms, logprefix, logfn)

		// Calling panic does not abort the process, because it is
		// caught by http server.

		if true {
			time.Sleep(1000 * time.Millisecond)
			force_quit_service()
		}
	case *proxy_exc:
		slogger.Error(logprefix+"Handler error", "err", err1)

		return_error_response(w, rqst, err1, delay_ms, logprefix, logfn)
	default:
		slogger.Error(logprefix+"Runtime panic", "err", err1,
			"stack", string(debug.Stack()))

		var err3 = &proxy_exc{
			"",
			"",
			http_500_internal_server_error,
			message_50x_internal_error,
			nil,
		}
		return_error_response(w, rqst, err3, delay_ms, logprefix, logfn)
	}
}

// CHECK_AUTHENTICATED checks the signature in an AWS Authorization
// Header.  It returns a secret_record or nil.  It may return
// (nil,nil) when an authorization header is missing.
func check_authenticated(m *multiplexer, r *http.Request) (*secret_record, *proxy_exc) {
	var header = r.Header.Get("Authorization")
	var cred authorization_s3v4 = scan_aws_authorization(header)
	if cred.signature == "" {
		return nil, nil
	}
	var auth string = cred.credential[0]
	var secret *secret_record = get_secret(m.table, auth)
	if secret == nil {
		slogger.Info(m.logprefix+"Bad credential", "key", auth,
			"reason", "unknown")
		var err1 = &proxy_exc{
			"",
			"",
			http_401_unauthorized,
			message_40x_access_rejected,
			nil,
		}
		return nil, err1
	}
	assert_fatal(secret.Access_key == auth)
	var keypair = [2]string{secret.Access_key, secret.Secret_key}
	var ok, reason1 = check_credential_is_good(r, keypair)
	if !ok {
		slogger.Info(m.logprefix+"Bad credential", "key", auth,
			"reason", reason1)
		var err2 = &proxy_exc{
			"",
			"",
			http_401_unauthorized,
			message_40x_access_rejected,
			nil,
		}
		return nil, err2
	}
	var expiration = time.Unix(secret.Expiration_time, 0)
	if !time.Now().Before(expiration) {
		slogger.Info(m.logprefix+"Bad credential", "key", auth,
			"reason", "expired")
		var err3 = &proxy_exc{
			"",
			"",
			http_403_forbidden,
			message_40x_access_rejected,
			nil,
		}
		return nil, err3
	}
	return secret, nil
}

// ENSURE_LENS3_IS_RUNNING checks if any Muxs are running.
func ensure_lens3_is_running__(t *keyval_table) bool {
	var muxs = list_mux_eps(t)
	return len(muxs) > 0
}

// ENSURE_BACKEND_RUNNING starts a backend if not running.  Returning
// nil by start_backend() is a fatal error.  Note that it updates an
// access timestamp before checking a backend.  It is to avoid a race
// in the start and stop of a backend.
func ensure_backend_running(m *multiplexer, w http.ResponseWriter, r *http.Request, pool string, auth string) *backend_record {
	set_pool_timestamp(m.table, pool)

	var be1 = get_backend(m.table, pool)
	if be1 == nil {
		//slogger.Info(m.logprefix+"Start backend", "pool", pool)
		var be2 = start_backend(m.manager, pool)
		if be2 == nil {
			// (An error is already logged).
			var err1 = &proxy_exc{
				auth,
				"",
				http_500_internal_server_error,
				message_500_cannot_start_backend,
				nil,
			}
			return_mux_error_response(m, w, r, err1)
			return nil
		}
		be1 = be2
	}

	switch be1.State {
	case pool_state_INITIAL, pool_state_READY:
		// Okay.
	case pool_state_DISABLED:
		panic(nil)
	case pool_state_SUSPENDED:
		slogger.Debug(m.logprefix+"Reject access to pool",
			"pool", pool, "reason", "suspended")
		var err2 = &proxy_exc{
			auth,
			"",
			http_503_service_unavailable,
			message_503_pool_suspended,
			nil,
		}
		return_mux_error_response(m, w, r, err2)
		return nil
	case pool_state_INOPERABLE:
		panic(nil)
	default:
		panic(nil)
	}

	return be1
}

// ENSURE_POOL_EXISTENCE checks a pool exists.  It should never fail.
// It is inconsistent if a bucket exists but a pool does not.
func ensure_pool_existence(m *multiplexer, w http.ResponseWriter, r *http.Request, pool string, auth string) *pool_record {
	var pooldata *pool_record = get_pool(m.table, pool)
	if pooldata == nil {
		slogger.Error("Inconsistency in keyval-db: bucket exists but no pool",
			"pool", pool)
		var err1 = &proxy_exc{
			auth,
			"",
			http_404_not_found,
			message_404_nonexisting_pool,
			nil,
		}
		return_mux_error_response(m, w, r, err1)
		return nil
	}
	return pooldata
}

// ENSURE_FORWARDING_HOST_TRUSTED checks the request sender is a
// frontend proxy or multiplexers.  It double checks m.mux_addrs,
// because mux_addrs is updated only when necessary.
func ensure_frontend_proxy_trusted(m *multiplexer, w http.ResponseWriter, r *http.Request) bool {
	//var peer = r.Header.Get("Remote_Addr")
	var peer = r.RemoteAddr
	if !check_frontend_proxy_trusted(m.trusted_proxies, peer) {
		slogger.Error(m.logprefix+"Untrusted frontend proxy", "ep", peer)
		var err1 = &proxy_exc{
			"",
			"",
			http_500_internal_server_error,
			message_500_access_rejected,
			nil,
		}
		return_mux_error_response(m, w, r, err1)
		return false
	}
	return true
}

// CHECK_BUCKET_IN_PATH returns a bucket record for the name in the
// path.  It may return (nil,nil) when a bucket name is missing in the
// path.  It does NOT check the owner of a bucket.
func check_bucket_in_path(m *multiplexer, w http.ResponseWriter, r *http.Request, auth string) (*bucket_record, *proxy_exc) {
	var name, err1 = pick_bucket_in_path(m, r, auth)
	if err1 != nil {
		return nil, err1
	}
	if name == "" {
		return nil, nil
	}
	// assert_fatal(name != "")
	var bucket = get_bucket(m.table, name)
	if bucket == nil {
		slogger.Info(m.logprefix+"Bad bucket", "bucket", name,
			"reason", "not found")
		var err2 = &proxy_exc{
			auth,
			"",
			http_404_not_found,
			message_404_no_named_bucket,
			nil,
		}
		return nil, err2
	}
	return bucket, nil
}

func ensure_bucket_not_expired(m *multiplexer, w http.ResponseWriter, r *http.Request, bucket *bucket_record, auth string) bool {
	var expiration = time.Unix(bucket.Expiration_time, 0)
	if !time.Now().Before(expiration) {
		slogger.Info(m.logprefix+"Bad bucket", "bucket", bucket.Bucket,
			"reason", "expired")
		var err1 = &proxy_exc{
			auth,
			"",
			http_403_forbidden,
			message_403_bucket_expired,
			nil,
		}
		return_mux_error_response(m, w, r, err1)
		return false
	}
	return true
}

func ensure_bucket_owner(m *multiplexer, w http.ResponseWriter, r *http.Request, bucket *bucket_record, secret *secret_record, auth string) bool {
	if bucket.Pool != secret.Pool {
		slogger.Info(m.logprefix+"Bad bucket", "bucket", bucket.Bucket,
			"reason", "not owner")
		var err1 = &proxy_exc{
			auth,
			"",
			http_403_forbidden,
			message_403_not_authorized,
			nil,
		}
		return_mux_error_response(m, w, r, err1)
		return false
	}
	return true
}

// ENSURE_POOL_STATE checks both a pool and its owner is active.
func ensure_pool_state(m *multiplexer, w http.ResponseWriter, r *http.Request, pooldata *pool_record, auth string) bool {
	var pool = pooldata.Pool
	var state1, _ = check_pool_is_usable(m.table, pooldata)
	switch state1 {
	case pool_state_INITIAL:
		panic(nil)
	case pool_state_READY:
		// Okay.
	case pool_state_DISABLED:
		slogger.Debug(m.logprefix+"Reject access to bad pool",
			"pool", pool, "reason", "disabled")
		var err2 = &proxy_exc{
			auth,
			"",
			http_403_forbidden,
			message_403_pool_disabled,
			nil,
		}
		return_mux_error_response(m, w, r, err2)
		return false
	case pool_state_SUSPENDED:
		panic(nil)
	case pool_state_INOPERABLE:
		slogger.Debug(m.logprefix+"Reject access to bad pool",
			"pool", pool, "reason", "inoperable")
		var err3 = &proxy_exc{
			auth,
			"",
			http_500_internal_server_error,
			message_500_pool_inoperable,
			nil,
		}
		return_mux_error_response(m, w, r, err3)
		return false
	default:
		panic(nil)
	}

	return true
}

func ensure_permission_by_secret(m *multiplexer, w http.ResponseWriter, r *http.Request, secret *secret_record, auth string) bool {
	var method string = r.Method
	var policy = secret.Secret_policy
	var set []secret_policy
	switch method {
	// "OPTIONS", "GET", "HEAD", "POST", "PUT", "DELETE", "TRACE",
	// "CONNECT", "PATCH"
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
		slogger.Warn(m.logprefix+"http unknown method", "method", method)
		set = []secret_policy{}
	}
	var ok = slices.Contains(set, policy)
	if !ok {
		slogger.Info(m.logprefix+"Bad secret", "key", secret.Access_key,
			"reason", "no permission", "pool", secret.Pool, "method", method)
		var err1 = &proxy_exc{
			auth,
			"",
			http_403_forbidden,
			message_403_no_permission,
			nil,
		}
		return_mux_error_response(m, w, r, err1)
		return false
	}
	return true
}

func ensure_permission_by_bucket(m *multiplexer, w http.ResponseWriter, r *http.Request, bucket *bucket_record, auth string) bool {
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
		slogger.Warn(m.logprefix+"http unknown method", "method", method)
		set = []bucket_policy{}
	}
	var ok = slices.Contains(set, policy)
	if !ok {
		slogger.Info(m.logprefix+"Bad bucket", "bucket", bucket.Bucket,
			"reason", "no permission", "pool", bucket.Pool, "method", method)
		var err1 = &proxy_exc{
			auth,
			"",
			http_403_forbidden,
			message_403_no_permission,
			nil,
		}
		return_mux_error_response(m, w, r, err1)
		return false
	}
	return true
}

// PICK_BUCKET_IN_PATH returns a bucket name in a request or "" when a
// bucket name is missing.  It may return an error.
func pick_bucket_in_path(m *multiplexer, r *http.Request, auth string) (string, *proxy_exc) {
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
		slogger.Info(m.logprefix+"Bad bucket naming", "bucket", bucket)
		var err1 = &proxy_exc{
			auth,
			"",
			http_400_bad_request,
			message_40x_access_rejected,
			nil,
		}
		return bucket, err1
	}
	return bucket, nil
}

// CHECK_POOL_IS_USABLE checks the state of a pool in changes of user
// and pool settings, and returns the subset of {READY, DISABLED,
// INOPERABLE}.  This routine should be called in access checking.
func check_pool_is_usable(t *keyval_table, pooldata *pool_record) (pool_state, pool_reason) {
	if pooldata == nil {
		// NEVER.
		return pool_state_INOPERABLE, pool_reason_POOL_REMOVED
	}

	// Check if a pool is in the INOPERABLE state.

	if pooldata.Inoperable {
		return pool_state_INOPERABLE, pooldata.Reason
	}

	// Check if a pool is in the DISABLED state.

	var uid = pooldata.Owner_uid
	var active, _ = check_user_is_active(t, uid)
	var online = pooldata.Enabled
	var expiration = time.Unix(pooldata.Expiration_time, 0)
	var unexpired = time.Now().Before(expiration)

	if !(active && online && unexpired) {
		if !active {
			return pool_state_DISABLED, pool_reason_USER_INACTIVE
		} else if !online {
			return pool_state_DISABLED, pool_reason_POOL_OFFLINE
		} else if !unexpired {
			return pool_state_DISABLED, pool_reason_POOL_EXPIRED
		} else {
			panic(nil)
		}
	}

	return pool_state_READY, pool_reason_NORMAL
}

// CHECK_POOL_IS_SUSPENED returns an approximate state which is used
// for reporting to users.  It returns in the subset {READY,
// SUSPENDED}.  It returns READY when the pool state is not recorded.
func check_pool_is_suspened(t *keyval_table, pool string) (pool_state, pool_reason) {
	var state *blurred_state_record = get_blurred_state(t, pool)
	if state == nil {
		return pool_state_READY, pool_reason_NORMAL
	}
	switch state.State {
	case pool_state_INITIAL:
		panic(nil)
	case pool_state_READY:
		return state.State, state.Reason
	case pool_state_DISABLED:
		panic(nil)
	case pool_state_SUSPENDED:
		return state.State, state.Reason
	case pool_state_INOPERABLE:
		panic(nil)
	default:
		panic(nil)
	}
}

// COMBINE_POOL_STATE merges the states, state1 from
// check_pool_is_usable() and state2 from check_pool_is_suspened().
func combine_pool_state(state1 pool_state, reason1 pool_reason, state2 pool_state, reason2 pool_reason) (pool_state, pool_reason) {
	switch state1 {
	case pool_state_INITIAL:
		panic(nil)
	case pool_state_READY:
		if state2 == pool_state_SUSPENDED {
			return state2, reason2
		} else {
			return state1, reason1
		}
	case pool_state_DISABLED:
		return state1, reason1
	case pool_state_SUSPENDED:
		panic(nil)
	case pool_state_INOPERABLE:
		return state1, reason1
	default:
		panic(nil)
	}
}

func check_user_is_active(t *keyval_table, uid string) (bool, string) {
	var ui = get_user(t, uid)
	if ui == nil {
		slogger.Info("Bad user", "user", uid, "reason", "not registered")
		return false, message_403_user_not_registered
	}
	var expiration = time.Unix(ui.Expiration_time, 0)
	if !ui.Enabled || !time.Now().Before(expiration) {
		slogger.Info("Bad user", "user", uid, "reason", "disabled")
		return false, message_403_user_disabled
	}

	var _, err1 = user.Lookup(uid)
	if err1 != nil {
		switch err1.(type) {
		case user.UnknownUserError:
		default:
			slogger.Error("user/Lookup() errs", "user", uid, "err", err1)
		}
		slogger.Warn("Bad user", "user", uid, "reason", "no account")
		return false, message_403_no_user_account
	}

	return true, ""
}

// RETURN_SUCCESS_RESPONSE_FOR_PROBE returns Okay response.  It is
// only for a probe access.
func return_success_response_for_probe(m *multiplexer, w http.ResponseWriter, r *http.Request, auth string) {
	var code = http_200_OK
	var rspn = &ui_success_response{
		Status:    status_success,
		Timestamp: time.Now().Unix(),
	}
	var b1, err1 = json.Marshal(rspn)
	assert_fatal(err1 == nil)
	var json1 = string(b1)
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.Header().Set("X-Content-Type-Options", "nosniff")
	w.WriteHeader(code)
	fmt.Fprintln(w, json1)
	log_mux_access_by_request(r, code, int64(len(json1)), "", auth)
}

func return_mux_error_response(m *multiplexer, w http.ResponseWriter, r *http.Request, err *proxy_exc) {
	var delay_ms = m.conf.Multiplexer.Error_response_delay_ms
	var logprefix = m.logprefix
	var logfn = log_mux_access_by_request
	return_error_response(w, r, err, delay_ms, logprefix, logfn)
}

func return_mux_error_response_no_delay(m *multiplexer, w http.ResponseWriter, r *http.Request, err *proxy_exc) {
	var delay_ms = time_in_ms(0)
	var logprefix = m.logprefix
	var logfn = log_mux_access_by_request
	return_error_response(w, r, err, delay_ms, logprefix, logfn)
}

// RETURN_ERROR_RESPONSE sends a response to a client.  It does not
// send details unless authenticated.
func return_error_response(w http.ResponseWriter, r *http.Request, err1 *proxy_exc, delay_ms time_in_ms, logprefix string, logfn access_logger) {
	var error1 string
	var info1 map[string]string
	if err1.auth == "" && err1.uid == "" {
		error1 = message_500_access_rejected
		info1 = nil
	} else {
		error1 = err1.error
		info1 = err1.info
	}
	var code1 = err1.code
	var rspn = &ui_error_response{
		Status: status_error,
		Reason: ui_error_reason{
			error1,
			info1,
		},
		Timestamp: time.Now().Unix(),
	}
	var b1, err2 = json.Marshal(rspn)
	assert_fatal(err2 == nil)
	var json1 = string(b1)
	delay_sleep(delay_ms)
	//http.Error(w, string(b1), code1)
	http_error_in_json(w, json1, code1)
	logfn(r, code1, int64(len(json1)), "", err1.auth)
}

// HTTP_ERROR_IN_JSON is http/Error() but content-type in json.
func http_error_in_json(w http.ResponseWriter, error string, code int) {
	//w.Header().Set("Content-Type", "text/plain; charset=utf-8")
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.Header().Set("X-Content-Type-Options", "nosniff")
	w.WriteHeader(code)
	fmt.Fprintln(w, error)
}
