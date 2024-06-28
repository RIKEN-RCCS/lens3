/* Lens3-Mux Main. */

// Copyright 2022-2024 RIKEN R-CCS.
// SPDX-License-Identifier: BSD-2-Clause

package lens3

// Multiplexer is a proxy to backend S3 servers -- Lens3's main part.

// NOTE: A request can be obtained from http.Response.Request in
// httputil.ReverseProxy.ModifyResponse, even although it is for
// server-side responses and the document says: "This is only
// populated for Client requests."

// NOTE: Do not call panic(http.ErrAbortHandler) to abort the
// processing of httputil.ReverseProxy.ErrorHandler.  Aborting does
// not send a response but closes a connection.

// MEMO:
//
// http.HandlerFunc is a function type.  It is
// (ResponseWriter,*Request)→unit

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
	//"flag"
	//"io"
	//"log"
	//"maps"
	//"os"
	//"runtime"
)

// MULTIPLEXER is a single object, "the_multiplexer".
type multiplexer struct {
	// MuxEP="Mux(ep)" is a printing name of this Multiplexer.
	MuxEP string

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
	// mux_addrs []string

	trusted_proxies []net.IP

	// CH_QUIT is to receive quitting notification.
	ch_quit_service <-chan vacuous

	server *http.Server

	mqtt *mqtt_client

	conf *mux_conf
}

// THE_MULTIPLEXER is the single multiplexer instance.
var the_multiplexer = &multiplexer{}

func configure_multiplexer(m *multiplexer, w *manager, t *keyval_table, qch <-chan vacuous, c *mux_conf) {
	m.table = t
	m.manager = w
	m.conf = c
	m.ch_quit_service = qch
	//m.verbose = true

	var conf = &m.conf.Multiplexer
	open_log_for_mux(c.Log.Access_log_file)

	var host string
	if conf.Mux_node_name != "" {
		host = conf.Mux_node_name
	} else {
		var h, err1 = os.Hostname()
		if err1 != nil {
			slogger.Error(m.MuxEP+" os.Hostname() failed", "err", err1)
			panic(nil)
		}
		host = h
	}
	var port = conf.Port
	m.ep_port = net.JoinHostPort("", strconv.Itoa(port))
	m.mux_ep = net.JoinHostPort(host, strconv.Itoa(port))
	m.mux_pid = os.Getpid()
	m.MuxEP = fmt.Sprintf("Mux(%s)", m.mux_ep)

	//conf.Forwarding_timeout = 60
	//m.client = &http.Client{}
	//m.proxy = m.client
	//conf.Front_host = "localhost"

	var addrs []net.IP = convert_hosts_to_addrs(conf.Trusted_proxy_list)
	slogger.Debug(m.MuxEP+" Trusted proxies", "ip", addrs)
	if len(addrs) == 0 {
		slogger.Error(m.MuxEP + " No trusted proxies")
		panic(nil)
	}
	m.trusted_proxies = addrs
}

// MEMO: ReverseProxy <: Handler as it implements ServeHTTP().
func start_multiplexer(m *multiplexer, wg *sync.WaitGroup) {
	if m.verbose {
		slogger.Debug(m.MuxEP + " start_multiplexer()")
	}

	go mux_periodic_work(m)

	var level = fetch_slogger_level(slogger)
	var loglogger = slog.NewLogLogger(slogger.Handler(), level)

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

	slogger.Info(m.MuxEP + " Start Multiplexer")
	var err1 = m.server.ListenAndServe()
	slogger.Error(m.MuxEP+" http.Server.ListenAndServe() DONE", "err", err1)
}

// PROXY_REQUEST_REWRITER is a function for ReverseProxy.Rewriter.  It
// receives the forwarding url from a filtering proxy via the context
// value "lens3-be".
func proxy_request_rewriter(m *multiplexer) func(*httputil.ProxyRequest) {
	return func(r *httputil.ProxyRequest) {
		var ctx = r.In.Context()
		var x1 = ctx.Value("lens3-be")
		var forwarding, ok = x1.(*url.URL)
		assert_fatal(ok)
		if false {
			slogger.Debug(m.MuxEP+" Forward a request", "url", forwarding)
		}
		r.SetURL(forwarding)
		r.SetXForwarded()
	}
}

// PROXY_ACCESS_ADDENDA makes a callback that is called at sending a
// response by httputil.ReverseProxy.  It is to generate an access
// log.
func proxy_access_addenda(m *multiplexer) func(*http.Response) error {
	return func(rspn *http.Response) error {
		if rspn.StatusCode != 200 {
			delay_sleep(m.conf.Multiplexer.Error_response_delay_ms)
		}
		var ctx = rspn.Request.Context()
		var x = ctx.Value("lens3-pool-auth")
		var poolauth, ok = x.([]string)
		var auth string = ""
		if ok {
			auth = poolauth[1]
		}
		log_mux_access_by_response(rspn, auth)
		return nil
	}
}

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
		slogger.Error((m.MuxEP + " httputil.ReverseProxy() failed;" +
			" Maybe a backend record outdated"), "pool", pool, "err", err)
		//delete_backend_exclusion(m.table, pool)
		//delete_backend(m.table, pool)

		var msg = message_internal_error
		var code = http_502_bad_gateway
		delay_sleep(m.conf.Multiplexer.Error_response_delay_ms)
		http.Error(w, msg, code)
		log_mux_access_by_request(rqst, code, int64(len(msg)), "-", auth)

		//panic(http.ErrAbortHandler)
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
			return_mux_error_response(m, w, r, err1)
			return
		}
		var auth string = "-"
		if authenticated != nil {
			auth = authenticated.Access_key
		}

		var bucket, err2 = check_bucket_in_path(m, w, r, auth)
		if err2 != nil {
			return_mux_error_response(m, w, r, err2)
			return
		}

		var probing = (authenticated != nil &&
			authenticated.Secret_policy == secret_policy_internal_access)
		switch {
		case probing:
			serve_internal_access(m, w, r, bucket, authenticated)
			return
		case bucket == nil && authenticated == nil:
			// THIS CAN BE PORT SCANS.
			if m.verbose {
				slogger.Debug(m.MuxEP + " Access the root")
			}
			var err4 = &proxy_exc{
				auth,
				http_400_bad_request,
				[][2]string{
					message_access_rejected,
				},
			}
			return_mux_error_response(m, w, r, err4)
			// return_mux_response(m, w, r,
			//  http_400_bad_request,
			// 	[][2]string{
			// 		message_access_rejected,
			// 	})
			return
		case bucket == nil && authenticated != nil:
			slogger.Debug(m.MuxEP + " Access the root with authentication")
			var err5 = &proxy_exc{
				auth,
				http_403_forbidden,
				[][2]string{
					message_bucket_listing_forbidden,
				},
			}
			return_mux_error_response(m, w, r, err5)
			// return_mux_response(m, w, r,
			//  http_403_forbidden,
			// 	[][2]string{
			// 		message_bucket_listing_forbidden,
			// 	})
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
	var auth = "-"
	if secret != nil {
		auth = secret.Access_key
	}
	var now int64 = time.Now().Unix()
	if !ensure_bucket_owner(m, w, r, bucket, secret, auth) {
		return
	}
	if !ensure_bucket_not_expired(m, w, r, bucket, now, auth) {
		return
	}
	var pooldata *pool_record = ensure_pool_existence(m, w, r, bucket.Pool, auth)
	if pooldata == nil {
		return
	}
	if !ensure_user_is_active(m, w, r, pooldata.Owner_uid, auth) {
		return
	}
	if !ensure_pool_state(m, w, r, pooldata.Pool, auth) {
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
	var auth = "-"
	var now int64 = time.Now().Unix()
	if !ensure_bucket_not_expired(m, w, r, bucket, now, auth) {
		return
	}
	var pooldata *pool_record = ensure_pool_existence(m, w, r, bucket.Pool, auth)
	if pooldata == nil {
		return
	}
	if !ensure_user_is_active(m, w, r, pooldata.Owner_uid, auth) {
		return
	}
	if !ensure_pool_state(m, w, r, pooldata.Pool, auth) {
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
		slogger.Error(m.MuxEP+" aws.signer.SignHTTP() failed", "err", err1)
		raise(&proxy_exc{
			auth,
			http_500_internal_server_error,
			[][2]string{
				message_sign_failed,
			},
		})
	}

	// Tell the forwarding endpoint to httputil.ReverseProxy.

	var pool = be.Pool
	var ep = be.Backend_ep
	var forwarding, err2 = url.Parse("http://" + ep)
	if err2 != nil {
		slogger.Error(m.MuxEP+" Bad backend ep", "ep", ep, "err", err2)
		raise(&proxy_exc{
			auth,
			http_500_internal_server_error,
			[][2]string{
				message_bad_backend_ep,
			},
		})
	}
	var ctx1 = r.Context()
	var ctx2 = context.WithValue(ctx1, "lens3-be", forwarding)
	var ctx3 = context.WithValue(ctx2, "lens3-pool-auth", []string{pool, auth})
	var r2 = r.WithContext(ctx3)

	if m.verbose {
		slogger.Debug(m.MuxEP+" Forward a request", "pool", pool, "key", auth,
			"method", r.Method, "resource", r.RequestURI)
	}

	proxy.ServeHTTP(w, r2)
}

// SERVE_INTERNAL_ACCESS handles requests by probe_access_mux() from
// Registrar or other Multiplexers.  A call to
// make_absent_buckets_in_backend() has a race, but it results in only
// redundant work.
func serve_internal_access(m *multiplexer, w http.ResponseWriter, r *http.Request, bucket *bucket_record, secret *secret_record) {
	assert_fatal(secret != nil)
	var auth = secret.Access_key
	slogger.Debug(m.MuxEP+" Internal access", "pool", secret.Pool)

	// REJECT REQUESTS FROM THE OUTSIDE.

	//var peer = r.Header.Get("Remote_Addr")
	//var peer = r.RemoteAddr

	var pool = secret.Pool
	var pooldata *pool_record = ensure_pool_existence(m, w, r, pool, auth)
	if pooldata == nil {
		return
	}
	if !ensure_user_is_active(m, w, r, pooldata.Owner_uid, auth) {
		return
	}
	if !ensure_pool_state(m, w, r, pooldata.Pool, auth) {
		return
	}

	var be = ensure_backend_running(m, w, r, secret.Pool, auth)
	if be == nil {
		return
	}

	make_absent_buckets_in_backend(m.manager, be)
}

type access_logger = func(rqst *http.Request, code int, length int64, uid string, auth string)

func handle_multiplexer_exc(m *multiplexer, w http.ResponseWriter, rqst *http.Request) {
	var delay_ms = m.conf.Multiplexer.Error_response_delay_ms
	var logfn = log_mux_access_by_request
	handle_exc(m.MuxEP, delay_ms, logfn, w, rqst)
}

func handle_exc(prefix string, delay_ms time_in_sec, logfn access_logger, w http.ResponseWriter, rqst *http.Request) {
	var x = recover()
	switch err1 := x.(type) {
	case nil:
	case *runtime.PanicNilError:
		slogger.Error(prefix+" FATAL ERROR", "err", err1)
		slogger.Error("stacktrace:\n" + string(debug.Stack()))
		var msg = message_internal_error
		var code = http_500_internal_server_error
		delay_sleep(delay_ms)
		http.Error(w, msg, code)
		logfn(rqst, code, int64(len(msg)), "-", "-")
		panic(nil)
		// case *table_exc:
		// 	slogger.Error(prefix+" keyval-db access error", "err", err1)
		// 	slogger.Error("stacktrace:\n" + string(debug.Stack()))
		// 	var msg = message_internal_error
		// 	var code = http_500_internal_server_error
		// 	delay_sleep(delay_ms)
		// 	http.Error(w, msg, code)
		// 	logfn(rqst, code, int64(len(msg)), "-")
	case *proxy_exc:
		slogger.Error(prefix+" Handled error", "err", err1)
		var msg = map[string]string{}
		for _, kv := range err1.message {
			msg[kv[0]] = kv[1]
		}
		var b1, err2 = json.Marshal(msg)
		assert_fatal(err2 == nil)
		delay_sleep(delay_ms)
		http.Error(w, string(b1), err1.code)
		logfn(rqst, err1.code, int64(len(b1)), "-", err1.auth)
	default:
		slogger.Error(prefix+" Runtime panic", "err", err1)
		slogger.Error("stacktrace:\n" + string(debug.Stack()))
		var msg = message_internal_error
		var code = http_500_internal_server_error
		delay_sleep(delay_ms)
		http.Error(w, msg, code)
		logfn(rqst, code, int64(len(msg)), "-", "-")
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
		slogger.Info(m.MuxEP+" Unknown credential", "key", auth)
		var err1 = &proxy_exc{
			"-",
			http_403_forbidden,
			[][2]string{
				message_access_rejected,
			},
		}
		return nil, err1
	}
	assert_fatal(secret.Access_key == auth)
	var keypair = [2]string{secret.Access_key, secret.Secret_key}
	var ok, reason = check_credential_in_request(r, keypair)
	if !ok {
		slogger.Info(m.MuxEP+" Bad credential",
			"key", auth, "reason", reason)
		var err2 = &proxy_exc{
			"-",
			http_403_forbidden,
			[][2]string{
				message_access_rejected,
			},
		}
		return nil, err2
	}
	var now = time.Now()
	var expiration = time.Unix(secret.Expiration_time, 0)
	if !now.Before(expiration) {
		var reason = "expired"
		slogger.Info(m.MuxEP+" Bad credential",
			"key", auth, "reason", reason)
		var err3 = &proxy_exc{
			"-",
			http_403_forbidden,
			[][2]string{
				message_access_rejected,
			},
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

// ENSURE_BACKEND_RUNNING starts a backend if not running.  Note that
// it updates an access timestamp before checking a backend.  It is to
// avoid a race in the start and stop of a backend.
func ensure_backend_running(m *multiplexer, w http.ResponseWriter, r *http.Request, pool string, auth string) *backend_record {
	set_access_timestamp(m.table, pool)

	var be1 = get_backend(m.table, pool)
	if be1 == nil {
		slogger.Info(m.MuxEP+" Start a backend", "pool", pool)
		var proc = start_backend(m.manager, pool)
		if proc == nil {
			var err1 = &proxy_exc{
				auth,
				http_500_internal_server_error,
				[][2]string{
					message_cannot_start_backend,
				},
			}
			return_mux_error_response(m, w, r, err1)
			// return_mux_response(m, w, r,
			// 	http_500_internal_server_error,
			// 	[][2]string{
			// 		message_cannot_start_backend,
			// 	})
			return nil
		}
	}

	var be2 = get_backend(m.table, pool)
	if be2 == nil {
		var err2 = &proxy_exc{
			auth,
			http_500_internal_server_error,
			[][2]string{
				message_backend_not_running,
			},
		}
		return_mux_error_response(m, w, r, err2)
		// return_mux_response(m, w, r,
		// 	http_500_internal_server_error,
		// 	[][2]string{
		// 		message_backend_not_running,
		// 	})
		return nil
	}
	return be2
}

// ENSURE_POOL_EXISTENCE checks the pool exists.  It should never fail.
// It is inconsistent if a bucket exists but a pool does not.
func ensure_pool_existence(m *multiplexer, w http.ResponseWriter, r *http.Request, pool string, auth string) *pool_record {
	var pooldata *pool_record = get_pool(m.table, pool)
	if pooldata == nil {
		var err1 = &proxy_exc{
			auth,
			http_404_not_found,
			[][2]string{
				message_nonexisting_pool,
			},
		}
		return_mux_error_response(m, w, r, err1)
		// return_mux_response(m, w, r,
		//  http_404_not_found,
		// 	[][2]string{
		// 		message_nonexisting_pool,
		// 	})
		return nil
	}
	return pooldata
}

func ensure_user_is_active(m *multiplexer, w http.ResponseWriter, r *http.Request, uid string, auth string) bool {
	var ok, reason = check_user_is_active(m.table, uid)
	if !ok {
		var err1 = &proxy_exc{
			auth,
			http_403_forbidden,
			[][2]string{
				reason,
			},
		}
		return_mux_error_response(m, w, r, err1)
		// return_mux_response(m, w, r,
		//  http_403_forbidden,
		// 	[][2]string{
		// 		reason,
		// 	})
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
		slogger.Error(m.MuxEP+" Frontend proxy is untrusted", "ep", peer)
		var err1 = &proxy_exc{
			"-",
			http_500_internal_server_error,
			[][2]string{
				//message_proxy_untrusted,
				message_access_rejected,
			},
		}
		return_mux_error_response(m, w, r, err1)
		// return_mux_response(m, w, r,
		//  http_500_internal_server_error,
		// 	[][2]string{
		// 		message_proxy_untrusted,
		// 	})
		return false
	}
	return true
}

// CHECK_BUCKET_IN_PATH returns a bucket record for the name in the
// path.  It may return (nil,nil) if a bucket name is missing in the
// path.  It returns a proxy_exc as an error.
func check_bucket_in_path(m *multiplexer, w http.ResponseWriter, r *http.Request, auth string) (*bucket_record, *proxy_exc) {
	var bucketname, err1 = pick_bucket_in_path(m, r, auth)
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
			auth,
			http_404_not_found,
			[][2]string{
				message_no_named_bucket,
			},
		}
		return nil, err2
	}
	return bucket, nil
}

func ensure_bucket_not_expired(m *multiplexer, w http.ResponseWriter, r *http.Request, bucket *bucket_record, now int64, auth string) bool {
	if bucket.Expiration_time < now {
		var err1 = &proxy_exc{
			auth,
			http_400_bad_request,
			[][2]string{
				message_bucket_expired,
			},
		}
		return_mux_error_response(m, w, r, err1)
		// return_mux_response(m, w, r,
		// 	http_400_bad_request,
		// 	[][2]string{
		// 		message_bucket_expired,
		// 	})
		return false
	}
	return true
}

func ensure_bucket_owner(m *multiplexer, w http.ResponseWriter, r *http.Request, bucket *bucket_record, secret *secret_record, auth string) bool {
	if bucket.Pool != secret.Pool {
		var err1 = &proxy_exc{
			auth,
			http_403_forbidden,
			[][2]string{
				message_not_authorized,
			},
		}
		return_mux_error_response(m, w, r, err1)
		// return_mux_response(m, w, r,
		//  http_403_forbidden,
		// 	[][2]string{
		// 		message_not_authorized,
		// 	})
		return false
	}
	return true
}

func ensure_pool_state(m *multiplexer, w http.ResponseWriter, r *http.Request, pool string, auth string) bool {
	var state, _ = check_pool_state(m.table, pool)
	switch state {
	case pool_state_INITIAL, pool_state_READY:
		// OK.
	case pool_state_SUSPENDED:
		slogger.Debug(m.MuxEP+" Reject an access; pool suspended",
			"pool", pool)
		var err1 = &proxy_exc{
			auth,
			http_503_service_unavailable,
			[][2]string{
				message_pool_suspended,
			},
		}
		return_mux_error_response(m, w, r, err1)
		// return_mux_response(m, w, r,
		// 	http_503_service_unavailable,
		// 	[][2]string{
		// 		message_pool_suspended,
		// 	})
		return false
	case pool_state_DISABLED:
		slogger.Debug(m.MuxEP+" Reject an access; pool disabled",
			"pool", pool)
		var err2 = &proxy_exc{
			auth,
			http_403_forbidden,
			[][2]string{
				message_pool_disabled,
			},
		}
		return_mux_error_response(m, w, r, err2)
		// return_mux_response(m, w, r,
		// 	http_403_forbidden,
		// 	[][2]string{
		// 		message_pool_disabled,
		// 	})
		return false
	case pool_state_INOPERABLE:
		slogger.Debug(m.MuxEP+" Reject an access; pool inoperable",
			"pool", pool)
		var err3 = &proxy_exc{
			auth,
			http_500_internal_server_error,
			[][2]string{
				message_pool_inoperable,
			},
		}
		return_mux_error_response(m, w, r, err3)
		// return_mux_response(m, w, r,
		// 	http_500_internal_server_error,
		// 	[][2]string{
		// 		message_pool_inoperable,
		// 	})
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
		slogger.Warn(m.MuxEP+" http unknown method", "method", method)
		set = []secret_policy{}
	}
	var ok = slices.Contains(set, policy)
	if !ok {
		var err1 = &proxy_exc{
			auth,
			http_403_forbidden,
			[][2]string{
				message_no_permission,
			},
		}
		return_mux_error_response(m, w, r, err1)
		// return_mux_response(m, w, r,
		// 	http_403_forbidden,
		// 	[][2]string{
		// 		message_no_permission,
		// 	})
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
		slogger.Warn(m.MuxEP+" http unknown method", "method", method)
		set = []bucket_policy{}
	}
	var ok = slices.Contains(set, policy)
	if !ok {
		var err1 = &proxy_exc{
			auth,
			http_403_forbidden,
			[][2]string{
				message_no_permission,
			},
		}
		return_mux_error_response(m, w, r, err1)
		// return_mux_response(m, w, r,
		// 	http_403_forbidden,
		// 	[][2]string{
		// 		message_no_permission,
		// 	})
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
		var err1 = &proxy_exc{
			auth,
			http_400_bad_request,
			[][2]string{
				message_bad_bucket_name,
			},
		}
		return bucket, err1
	}
	return bucket, nil
}

//func return_mux_response(m *multiplexer, w http.ResponseWriter,
//	r *http.Request, code int, message [][2]string)

func return_mux_error_response(m *multiplexer, w http.ResponseWriter, r *http.Request, err error) {
	switch err1 := err.(type) {
	default:
		slogger.Error(m.MuxEP+" Unexpected error (internal)", "err", err)
		raise(err)
	case *proxy_exc:
		// Do not send details if not authenticated.
		var message [][2]string
		if err1.auth == "-" {
			message = [][2]string{
				message_access_rejected,
			}
		} else {
			message = err1.message
		}
		var msg = map[string]string{}
		for _, kv := range message {
			msg[kv[0]] = kv[1]
		}
		var now = time.Now().Unix()
		var rspn = &error_response{
			response_common: response_common{
				Status:    "error",
				Reason:    msg,
				Timestamp: now,
			},
		}
		var b1, err2 = json.Marshal(rspn)
		assert_fatal(err2 == nil)
		delay_sleep(m.conf.Multiplexer.Error_response_delay_ms)
		http.Error(w, string(b1), err1.code)
		log_mux_access_by_request(r, err1.code, int64(len(b1)), "-", err1.auth)
	}
}

func mux_periodic_work(m *multiplexer) {
	var conf = &m.conf.Multiplexer
	if m.verbose {
		//slogger.Debug(m.MuxEP + " Periodic work started")
	}
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
			slogger.Debug(m.MuxEP + " Update Mux-ep")
		}
		mux.Timestamp = time.Now().Unix()
		set_mux_ep(m.table, m.mux_ep, mux)
		var ok = set_mux_ep_expiry(m.table, m.mux_ep, expiry)
		if !ok {
			// Ignore an error.
			slogger.Error(m.MuxEP + " Bad call set_mux_ep_expiry()")
		}
		var jitter = rand.Int64N(interval / 8)
		time.Sleep(time.Duration(interval+jitter) * time.Second)
	}
}

// CHECK_POOL_STATE checks the changes of user and pool settings.  It
// returns a state and a reason.  It also updates the state of the
// pool.  This code should be called in the pass of access checking.
func check_pool_state(t *keyval_table, pool string) (pool_state, pool_reason) {
	var pooldata = get_pool(t, pool)
	if pooldata == nil {
		return pool_state_INOPERABLE, pool_reason_POOL_REMOVED
	}
	var state *pool_state_record = get_pool_state(t, pool)
	if state == nil {
		slogger.Warn("Pool state not found (ignored)", "pool", pool)
		var now int64 = time.Now().Unix()
		state = &pool_state_record{
			Pool:      pool,
			State:     pool_state_INITIAL,
			Reason:    pool_reason_NORMAL,
			Timestamp: now,
		}
		set_pool_state(t, pool, state.State, state.Reason)
	}

	// Check a state transition.

	switch state.State {
	case pool_state_INITIAL, pool_state_READY:
	case pool_state_SUSPENDED:
	case pool_state_DISABLED:
	case pool_state_INOPERABLE:
		return state.State, state.Reason
	default:
		panic(nil)
	}

	var uid = pooldata.Owner_uid
	var active, _ = check_user_is_active(t, uid)
	var online = pooldata.Enabled
	var expiration = time.Unix(pooldata.Expiration_time, 0)
	var unexpired = time.Now().Before(expiration)

	if !(active && online && unexpired) {
		if state.State != pool_state_DISABLED {
			state.State = pool_state_DISABLED
			if !active {
				state.Reason = pool_reason_USER_INACTIVE
			} else if !online {
				state.Reason = pool_reason_POOL_OFFLINE
			} else if !unexpired {
				state.Reason = pool_reason_POOL_EXPIRED
			} else {
				panic(nil)
			}
			set_pool_state(t, pool, state.State, state.Reason)
			return state.State, state.Reason
		}
		return state.State, state.Reason
	}

	var be = get_backend(t, pool)
	if be != nil {
		switch be.State {
		case pool_state_INITIAL:
			panic(nil)
		case pool_state_READY:
			return pool_state_READY, pool_reason_NORMAL
		case pool_state_SUSPENDED:
			return pool_state_SUSPENDED, pool_reason_SERVER_BUSY
		case pool_state_DISABLED, pool_state_INOPERABLE:
			panic(nil)
		default:
			panic(nil)
		}
	}

	switch state.State {
	case pool_state_INITIAL, pool_state_READY:
	case pool_state_SUSPENDED:
	case pool_state_DISABLED:
		state.State = pool_state_INITIAL
		state.Reason = pool_reason_NORMAL
		set_pool_state(t, pool, state.State, state.Reason)
	case pool_state_INOPERABLE:
		panic(nil)
	default:
		panic(nil)
	}
	return state.State, state.Reason
}

func check_user_is_active(t *keyval_table, uid string) (bool, error_message) {
	var now int64 = time.Now().Unix()
	var ui = get_user(t, uid)
	if ui == nil {
		slogger.Warn("User not found", "user", uid)
		return false, message_user_not_registered
	}
	if !ui.Enabled || ui.Expiration_time < now {
		return false, message_user_disabled
	}

	var _, err1 = user.Lookup(uid)
	if err1 != nil {
		switch err1.(type) {
		case user.UnknownUserError:
		default:
			slogger.Error("user.Lookup() returns a bad error",
				"user", uid, "err", err1)
		}
		slogger.Warn("user.Lookup() fails", "user", uid, "err", err1)
		return false, message_no_user_account
	}
	// (uu.Uid : string, uu.Gid : string)

	return true, error_message{}
}
