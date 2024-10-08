/* Lens3-Registrar.  Registrar of buckets and secrets. */

// Copyright 2022-2024 RIKEN R-CCS
// SPDX-License-Identifier: BSD-2-Clause

package lens3

// Registrar is a Web-UI for pool management.

// NOTE: Registrar uses a "double submit cookie" for CSRF prevention,
// that is used in fastapi_csrf_protect.  It uses a cookie+header
// pair.  A cookie is "fastapi-csrf-token" and a header is
// "X-Csrf-Token".  A response of GET "/user_info" sets the CSRF state
// in a client.  See https://github.com/aekasitt/fastapi-csrf-protect

// NOTE: An URL to http.Redirect includes a host:port that matches the
// pattern in the Apache "ProxyPassReverse" directive.  Otherwise,
// rewriting by the proxy fails.  A status code can be one of
// {StatusMovedPermanently(301), StatusSeeOther(303),
// StatusTemporaryRedirect(307), StatusPermanentRedirect(308)}.

// MEMO: UI expects responses as FastAPI/Starlette's "JSONResponse".
//
// media_type = "application/json"
// json.dumps(
//   content,
//   ensure_ascii=False,
//   allow_nan=False,
//   indent=None,
//   separators=(",", ":"),
// ).encode("utf-8")

// MEMO: Arrays are initialed by "make(type,0)" if they are to be
// returned to UI in json.  It makes an empty json entry "key:[]"
// instead of "key:null".

// MEMO: Maybe, consider adding a "Retry-After" header for 503 error.

import (
	"context"
	"encoding/json"
	"fmt"
	"math/rand/v2"
	"net"
	"net/http"
	"os/user"
	"path/filepath"
	"runtime/debug"
	"slices"
	"strconv"
	"strings"
	"sync"
	"time"
)

// UI scripts are stored in Golang's embedded files.
import "embed"

//go:embed ui
var efs1 embed.FS

//go:embed ui2
var efs2 embed.FS

const reg_api_version = "v1.2"

// REGISTRAR is a record of Registrar.  EP_PORT is a listening port of
// Registrar (":port").  CH_QUIT_SERVICE is a receiver of a quit
// notification.
type registrar struct {
	ep_port string

	table *keyval_table

	trusted_proxies []net.IP

	ch_quit_service <-chan vacuous

	server *http.Server

	conf *reg_conf
}

// Records exchanged via Web-UI.  These are returned in json.
// XXX_RESPONSE records are returned to UI.  XXX_REQUEST records are
// passed from UI.  Status is "success" or "error".  Decoding a
// response with "ui_error_response" works for both successful or
// failure cases.  See the function set_pool_data() in
// "v1/ui/src/lens3c.ts" for responses UI expects.  These are
// compatible to version v1.3.

type ui_response_status string

const (
	status_success ui_response_status = "success"
	status_error   ui_response_status = "error"
)

type ui_success_response struct {
	Status    ui_response_status `json:"status"`
	Timestamp int64              `json:"time"`
}

type ui_error_response struct {
	Status    ui_response_status `json:"status"`
	Reason    ui_error_reason    `json:"reason"`
	Timestamp int64              `json:"time"`
}

type ui_error_extra map[string]string
type ui_error_reason struct {
	Error string         `json:"error"`
	Info  ui_error_extra `json:"info"`
}

type ui_user_info_response struct {
	ui_success_response
	Csrf_token string       `json:"x_csrf_token"`
	User_info  user_info_ui `json:"user_info"`
}

type ui_pool_prop_response struct {
	ui_success_response
	Pool_prop *pool_prop_ui `json:"pool_desc"`
}

type ui_pool_list_response struct {
	ui_success_response
	Pool_list []*pool_prop_ui `json:"pool_list"`
}

type pool_prop_ui struct {
	Pool                string            `json:"pool_name"`
	Bucket_directory    string            `json:"buckets_directory"`
	Owner_uid           string            `json:"owner_uid"`
	Owner_gid           string            `json:"owner_gid"`
	Buckets             []*bucket_data_ui `json:"buckets"`
	Secrets             []*secret_data_ui `json:"secrets"`
	Probe_key           string            `json:"probe_key"`
	Expiration_time     int64             `json:"expiration_time"`
	Online_status       bool              `json:"online_status"`
	User_enabled_status bool              `json:"user_enabled_status"`
	Backend_state       pool_state        `json:"minio_state"`
	Backend_reason      pool_reason       `json:"minio_reason"`
	Timestamp           int64             `json:"modification_time"`
}

type bucket_data_ui struct {
	Pool          string `json:"pool"`
	Bucket        string `json:"name"`
	Bucket_policy string `json:"bkt_policy"`
	Timestamp     int64  `json:"modification_time"`
}

type secret_data_ui struct {
	Pool            string `json:"owner"`
	Access_key      string `json:"access_key"`
	Secret_key      string `json:"secret_key"`
	Secret_policy   string `json:"key_policy"`
	Expiration_time int64  `json:"expiration_time"`
	Timestamp       int64  `json:"modification_time"`
}

type user_info_ui struct {
	Api_version   string   `json:"api_version"`
	Uid           string   `json:"uid"`
	Groups        []string `json:"groups"`
	Lens3_version string   `json:"lens3_version"`
	S3_url        string   `json:"s3_url"`
	Footer_banner string   `json:"footer_banner"`
}

type make_pool_request struct {
	Bucket_directory string `json:"buckets_directory"`
	Owner_gid        string `json:"owner_gid"`
}

type make_bucket_request struct {
	Bucket        string `json:"name"`
	Bucket_policy string `json:"bkt_policy"`
}

type make_secret_request struct {
	Secret_policy   string `json:"key_policy"`
	Expiration_time int64  `json:"expiration_time"`
}

const (
	bucket_policy_ui_NONE string = "none"
	bucket_policy_ui_WO   string = "upload"
	bucket_policy_ui_RO   string = "download"
	bucket_policy_ui_RW   string = "public"
)

var export_bucket_policy_to_ui = map[bucket_policy]string{
	bucket_policy_NONE: bucket_policy_ui_NONE,
	bucket_policy_WO:   bucket_policy_ui_WO,
	bucket_policy_RO:   bucket_policy_ui_RO,
	bucket_policy_RW:   bucket_policy_ui_RW,
}

var intern_bucket_policy_from_ui = map[string]bucket_policy{
	bucket_policy_ui_NONE: bucket_policy_NONE,
	bucket_policy_ui_WO:   bucket_policy_WO,
	bucket_policy_ui_RO:   bucket_policy_RO,
	bucket_policy_ui_RW:   bucket_policy_RW,
}

const (
	secret_policy_ui_RW string = "readwrite"
	secret_policy_ui_RO string = "readonly"
	secret_policy_ui_WO string = "writeonly"
)

var export_secret_policy_to_ui = map[secret_policy]string{
	secret_policy_RW: secret_policy_ui_RW,
	secret_policy_RO: secret_policy_ui_RO,
	secret_policy_WO: secret_policy_ui_WO,
}

var intern_secret_policy_from_ui = map[string]secret_policy{
	secret_policy_ui_RW: secret_policy_RW,
	secret_policy_ui_RO: secret_policy_RO,
	secret_policy_ui_WO: secret_policy_WO,
}

var the_registrar = &registrar{}

// REG_BAD_ARGUMENT_MESSAGE is a partial error message to be returned
// to Web-UI on bad arguments.  It is copied to proxy_exc.  See
// decode_request_body_with_error_return().
type reg_bad_argument_message struct {
	error string
	info  map[string]string
}

func configure_registrar(z *registrar, t *keyval_table, qch <-chan vacuous, c *reg_conf) {
	z.table = t
	z.ch_quit_service = qch
	z.conf = c

	var conf = &z.conf.Registrar
	open_log_for_reg(c.Log.Access_log_file)

	z.ep_port = net.JoinHostPort("", strconv.Itoa(conf.Port))

	var addrs []net.IP = convert_hosts_to_addrs(conf.Trusted_proxy_list)
	slogger.Debug("Reg: Trusted proxies", "ip", addrs)
	if len(addrs) == 0 {
		slogger.Error("Reg: No trusted proxies")
		panic(nil)
	}
	z.trusted_proxies = addrs
}

func start_registrar(z *registrar, wg *sync.WaitGroup) {
	defer func() {
		var x = recover()
		if x != nil {
			slogger.Error("Reg: Registrar main errs", "err", x,
				"stack", string(debug.Stack()))
		}
	}()
	defer wg.Done()
	defer force_quit_service()

	if trace_task&tracing != 0 {
		slogger.Debug("Reg: start_registrar()")
	}

	var router = http.NewServeMux()
	z.server = &http.Server{
		Addr:    z.ep_port,
		Handler: router,
		//ErrorLog *log.Logger,
		//BaseContext func(net.Listener) context.Context,
	}

	// Root "/" requests are redirected.

	router.HandleFunc("GET /{$}", func(w http.ResponseWriter, r *http.Request) {
		defer handle_registrar_exc(z, w, r)
		var ep = z.conf.Registrar.Server_ep
		var newurl = "http://" + ep + "/ui/index.html"
		slogger.Debug("Reg: http GET /", "redirect", newurl)
		http.Redirect(w, r, newurl, http.StatusTemporaryRedirect)
	})

	router.HandleFunc("GET /ui/index.html", func(w http.ResponseWriter, r *http.Request) {
		defer handle_registrar_exc(z, w, r)
		slogger.Debug("Reg: http GET /ui/index.html")
		var _ = return_file(z, w, r, r.URL.Path, true, &efs1)
	})

	router.HandleFunc("GET /ui2/index.html", func(w http.ResponseWriter, r *http.Request) {
		defer handle_registrar_exc(z, w, r)
		slogger.Debug("Reg: http GET /ui2/index.html")
		var _ = return_file(z, w, r, r.URL.Path, true, &efs2)
	})

	router.HandleFunc("GET /ui/", func(w http.ResponseWriter, r *http.Request) {
		defer handle_registrar_exc(z, w, r)
		slogger.Debug("Reg: http GET /ui/", "path", r.URL.Path)
		var _ = return_file(z, w, r, r.URL.Path, false, &efs1)
	})

	router.HandleFunc("GET /ui2/", func(w http.ResponseWriter, r *http.Request) {
		defer handle_registrar_exc(z, w, r)
		slogger.Debug("Reg: http GET /ui2/", "path", r.URL.Path)
		var _ = return_file(z, w, r, r.URL.Path, false, &efs2)
	})

	router.HandleFunc("GET /user-info", func(w http.ResponseWriter, r *http.Request) {
		defer handle_registrar_exc(z, w, r)
		slogger.Debug("Reg: http GET /user-info")
		var _ = return_user_info(z, w, r)
	})

	router.HandleFunc("GET /pool", func(w http.ResponseWriter, r *http.Request) {
		defer handle_registrar_exc(z, w, r)
		slogger.Debug("Reg: http GET /pool")
		var _ = list_pool_and_return_response(z, w, r, "")
	})

	router.HandleFunc("GET /pool/{pool}", func(w http.ResponseWriter, r *http.Request) {
		defer handle_registrar_exc(z, w, r)
		var pool = r.PathValue("pool")
		slogger.Debug("Reg: http GET /pool", "pool", pool)
		var _ = list_pool_and_return_response(z, w, r, pool)
	})

	// A POST request makes a pool.

	router.HandleFunc("POST /pool", func(w http.ResponseWriter, r *http.Request) {
		defer handle_registrar_exc(z, w, r)
		slogger.Debug("Reg: http POST /pool")
		var _ = make_pool_and_return_response(z, w, r)
	})

	router.HandleFunc("DELETE /pool/{pool}", func(w http.ResponseWriter, r *http.Request) {
		defer handle_registrar_exc(z, w, r)
		var pool = r.PathValue("pool")
		slogger.Debug("Reg: http DELETE /pool", "pool", pool)
		var _ = delete_pool_and_return_response(z, w, r, pool)
	})

	// A PUT request makes a bucket.

	router.HandleFunc("PUT /pool/{pool}/bucket", func(w http.ResponseWriter, r *http.Request) {
		defer handle_registrar_exc(z, w, r)
		var pool = r.PathValue("pool")
		slogger.Debug("Reg: http PUT /pool/*/bucket", "pool", pool)
		var _ = make_bucket_and_return_response(z, w, r, pool)
	})

	router.HandleFunc("DELETE /pool/{pool}/bucket/{bucket}", func(w http.ResponseWriter, r *http.Request) {
		defer handle_registrar_exc(z, w, r)
		var pool = r.PathValue("pool")
		var bucket = r.PathValue("bucket")
		slogger.Debug("Reg: http DELETE /pool/*/bucket", "pool", pool,
			"bucket", bucket)
		var _ = delete_bucket_and_return_response(z, w, r, pool, bucket)
	})

	// A POST request makes a secret.

	router.HandleFunc("POST /pool/{pool}/secret", func(w http.ResponseWriter, r *http.Request) {
		defer handle_registrar_exc(z, w, r)
		var pool = r.PathValue("pool")
		slogger.Debug("Reg: http POST /pool/*/secret", "pool", pool)
		var _ = make_secret_and_return_response(z, w, r, pool)
	})

	router.HandleFunc("DELETE /pool/{pool}/secret/{secret}", func(w http.ResponseWriter, r *http.Request) {
		defer handle_registrar_exc(z, w, r)
		var pool = r.PathValue("pool")
		var secret = r.PathValue("secret")
		slogger.Debug("Reg: http DELETE /pool/*/secret", "pool", pool,
			"secret", secret)
		var _ = delete_secret_and_return_response(z, w, r, pool, secret)
	})

	go func() {
		select {
		case <-z.ch_quit_service:
			var ctx = context.Background()
			z.server.Shutdown(ctx)
		}
	}()

	slogger.Info("Reg: Start Registrar", "ep", z.ep_port)
	var err1 = z.server.ListenAndServe()
	slogger.Error("Reg: http/Server.ListenAndServe() EXITS", "err", err1)
}

// HANDLE_REGISTRAR_EXC should be called by defer, directly.
func handle_registrar_exc(z *registrar, w http.ResponseWriter, rqst *http.Request) {
	var x = recover()
	var delay_ms = z.conf.Registrar.Error_response_delay_ms
	var logprefix = "Reg: "
	var logfn = log_reg_access_by_request
	handle_exc(x, w, rqst, delay_ms, logprefix, logfn)
}

func return_file(z *registrar, w http.ResponseWriter, rqst *http.Request, path string, modify_script bool, efs *embed.FS) *[]byte {
	var path1 string
	if len(path) >= 1 && path[0] == '/' {
		path1 = path[1:]
	} else {
		path1 = path
	}
	var data1, err1 = efs.ReadFile(path1)
	if err1 != nil {
		slogger.Error("Reg: Reading UI files failed",
			"path", path1, "err", err1)
		delay_sleep(z.conf.Registrar.Error_response_delay_ms)
		var msg = "BAD"
		var code = http_500_internal_server_error
		http.Error(w, msg, code)
		log_reg_access_by_request(rqst, code, int64(len(msg)), "", "")
		return nil
	}

	var data2 []byte
	if modify_script {
		var parameters = (`<script type="text/javascript">const base_path_="` +
			z.conf.Registrar.Base_path + `";</script>`)
		var x = strings.Replace(string(data1),
			"PLACE_BASE_PATH_SETTING_HERE", parameters, 1)
		//fmt.Println(string(x))
		data2 = []byte(x)
	} else {
		data2 = data1
	}

	switch filepath.Ext(path1) {
	case ".html":
		w.Header().Set("Content-Type", "text/html; charset=utf-8")
	case ".css":
		w.Header().Set("Content-Type", "text/css; charset=utf-8")
	case ".js":
		w.Header().Set("Content-Type", "text/javascript; charset=utf-8")
	default:
		//favicon.ico -> "image/png"
		//materialdesignicons-webfont.ttf
		//materialdesignicons-webfont.eot
		//materialdesignicons-webfont.woff
		//materialdesignicons-webfont.woff2 -> "font/woff2"
		//materialdesignicons.css.map -> "text/plain"
		var ct = http.DetectContentType(data2)
		if trace_proxy&tracing != 0 {
			slogger.Debug("Reg: http/DetectContentType()",
				"path", path1, "type", ct)
		}
		w.Header().Set("Content-Type", (ct + "; charset=utf-8"))
	}

	var _, err2 = w.Write(data2)
	if err2 != nil {
		slogger.Error("Reg: Writing reply failed", "err", err2)
	}
	var wf, ok = w.(http.Flusher)
	if ok {
		wf.Flush()
	}
	log_reg_access_by_request(rqst, 200, int64(len(data2)), "", "")
	return &data1
}

// RETURN_USER_INFO returns a response for GET "/user-info".  This
// request is assumed as the first request, and it initializes the
// CSRF state.  u.Ephemeral=true means the user was added
// automatically.  It makes a list of groups each time for such a
// user, because groups may be changed.  The groups can be empty, but
// that user cannot create a new pool.
func return_user_info(z *registrar, w http.ResponseWriter, r *http.Request) *ui_user_info_response {
	var conf = &z.conf.Registrar
	var opr = "user-info"

	var u = check_user_access_with_error_return(z, w, r, "", true)
	if u == nil {
		return nil
	}
	if !check_empty_arguments_with_error_return(z, w, r, u, "", opr) {
		return nil
	}

	var groups []string
	if !u.Ephemeral {
		groups = u.Groups
	} else {
		groups = list_groups_of_user(z, u.Uid)
	}

	var info = copy_user_record_to_ui(z, u, groups)
	var csrf = make_csrf_tokens(z, u.Uid)
	var timeout = int64(conf.Ui_session_duration)
	//var expiration = time.Now().Add(timeout * time.Second)
	var cookie = &http.Cookie{
		Name:  "fastapi-csrf-token",
		Value: csrf.Csrf_token[0],
		Path:  "/",
		//Domain:
		//Expires: expiration,
		MaxAge:   int(timeout),
		Secure:   false,
		HttpOnly: true,
		SameSite: http.SameSiteDefaultMode,
		//Raw:
		//Unparsed:
	}
	http.SetCookie(w, cookie)
	var now = time.Now().Unix()
	var rspn = &ui_user_info_response{
		ui_success_response: ui_success_response{
			Status:    status_success,
			Timestamp: now,
		},
		Csrf_token: csrf.Csrf_token[1],
		User_info:  *info,
	}
	return_success_repsonse(z, w, r, u, rspn)
	return rspn
}

// LIST_POOL_AND_RETURN_RESPONSE returns a record of a pool, given a
// pool-name, or a list of pools owned by a user if pool="".
func list_pool_and_return_response(z *registrar, w http.ResponseWriter, r *http.Request, pool string) *ui_pool_list_response {
	var opr = "list-pool"

	var u = check_user_access_with_error_return(z, w, r, pool, false)
	if u == nil {
		return nil
	}
	if !check_empty_arguments_with_error_return(z, w, r, u, pool, opr) {
		return nil
	}

	var namelist = list_pools(z.table, ITE(pool == "", "*", pool))
	var poollist []*pool_prop_ui = make([]*pool_prop_ui, 0)
	for _, name := range namelist {
		var d = gather_pool_prop(z.table, name)
		if d != nil && d.Owner_uid == u.Uid {
			poollist = append(poollist, copy_pool_prop_to_ui(d))
		}
	}

	if pool != "" && len(poollist) == 0 {
		var err1 = &proxy_exc{
			"",
			u.Uid,
			http_404_not_found,
			message_404_no_pool,
			map[string]string{
				"pool": pool,
			},
		}
		return_reg_error_response(z, w, r, err1)
		return nil
	}
	if pool != "" && len(poollist) > 1 {
		slogger.Error("Reg: Multiple pools with the same id", "pool", pool)
		var err2 = &proxy_exc{
			"",
			u.Uid,
			http_500_internal_server_error,
			message_500_inconsistent_db,
			nil,
		}
		return_reg_error_response(z, w, r, err2)
		return nil
	}

	slices.SortFunc(poollist, func(x, y *pool_prop_ui) int {
		return strings.Compare(x.Bucket_directory, y.Bucket_directory)
	})
	var rspn = &ui_pool_list_response{
		ui_success_response: ui_success_response{
			Status:    status_success,
			Timestamp: time.Now().Unix(),
		},
		Pool_list: poollist,
	}
	return_success_repsonse(z, w, r, u, rspn)
	return rspn
}

// MAKE_POOL_AND_RETURN_RESPONSE performs a make-pool operation.  An
// error in probe_access_mux() is ignored, in order to display the
// error condition in the pool "state" field in Web-UI.
func make_pool_and_return_response(z *registrar, w http.ResponseWriter, r *http.Request) *ui_pool_prop_response {
	var opr = "make-pool"

	var u = check_user_access_with_error_return(z, w, r, "", false)
	if u == nil {
		return nil
	}

	var args make_pool_request
	if !decode_request_body_with_error_return(z, w, r, u, "", opr,
		&args, check_make_pool_request) {
		return nil
	}

	var now int64 = time.Now().Unix()

	// Register pool-name.

	var poolname = &pool_name_record{
		Owner_uid: u.Uid,
		Timestamp: now,
	}
	var pool = set_with_unique_pool_name(z.table, poolname)

	// Register bucket-directory.

	var path = args.Bucket_directory
	var bd = &bucket_directory_record{
		Pool:      pool,
		Directory: path,
		Timestamp: now,
	}
	var ok, holder = set_ex_bucket_directory(z.table, path, bd)
	if !ok {
		var _ = delete_pool_name_checking(z.table, pool)
		var owner = find_owner_of_pool(z, holder)
		var err1 = &proxy_exc{
			"",
			u.Uid,
			http_409_conflict,
			message_409_bucket_directory_already_taken,
			map[string]string{
				"path":  path,
				"owner": owner,
			},
		}
		return_reg_error_response(z, w, r, err1)
		return nil
	}

	var conf = &z.conf.Registrar
	assert_fatal(conf.Pool_expiration_days > 0)
	var days = conf.Pool_expiration_days.time_duration()
	var expiration = time.Now().Add(days).Unix()

	// Register secret for probing.

	var secret = &secret_record{
		Pool:            pool,
		Access_key:      "",
		Secret_key:      generate_secret_key(),
		Secret_policy:   secret_policy_internal_access,
		Expiration_time: expiration,
		Timestamp:       now,
	}
	var probe = set_with_unique_secret_key(z.table, secret)

	// Register pool.

	var pooldata = &pool_record{
		Pool:             pool,
		Bucket_directory: path,
		Owner_uid:        u.Uid,
		Owner_gid:        args.Owner_gid,
		Probe_key:        probe,
		Enabled:          true,
		Expiration_time:  expiration,
		Timestamp:        now,
	}
	set_pool(z.table, pool, pooldata)
	//set_pool_state(z.table, pool, pool_state_INITIAL, pool_reason_NORMAL)

	var _ = probe_access_mux(z.table, pool)
	// (An error is already logged).

	var rspn = return_pool_prop(z, w, r, u, pool)
	return rspn
}

func delete_pool_and_return_response(z *registrar, w http.ResponseWriter, r *http.Request, pool string) *ui_success_response {
	var opr = "delete-pool"

	var u = check_user_access_with_error_return(z, w, r, pool, false)
	if u == nil {
		return nil
	}
	if !check_empty_arguments_with_error_return(z, w, r, u, pool, opr) {
		return nil
	}

	var ok = deregister_pool(z.table, pool)
	if !ok {
		var err1 = &proxy_exc{
			"",
			u.Uid,
			http_404_not_found,
			message_404_no_pool,
			map[string]string{
				"pool": pool,
			},
		}
		return_reg_error_response(z, w, r, err1)
		return nil
	}

	// activate_backend(pool)
	// disable_backend_secrets()
	// disable_backend_buckets()

	var rspn = &ui_success_response{
		Status:    status_success,
		Timestamp: time.Now().Unix(),
	}
	return_success_repsonse(z, w, r, u, rspn)
	return rspn
}

func make_bucket_and_return_response(z *registrar, w http.ResponseWriter, r *http.Request, pool string) *ui_pool_prop_response {
	var opr = "make-bucket"

	var u = check_user_access_with_error_return(z, w, r, pool, false)
	if u == nil {
		return nil
	}

	var args make_bucket_request
	if !decode_request_body_with_error_return(z, w, r, u, pool, opr,
		&args, check_make_bucket_request) {
		return nil
	}
	var name = args.Bucket
	var policy = intern_bucket_policy_from_ui[args.Bucket_policy]
	// (Arguments are checked above).
	assert_fatal(policy != "")

	var conf = &z.conf.Registrar
	assert_fatal(conf.Bucket_expiration_days > 0)
	var days = conf.Bucket_expiration_days.time_duration()
	var expiration = time.Now().Add(days).Unix()

	var bucket = &bucket_record{
		Pool:            pool,
		Bucket:          name,
		Bucket_policy:   policy,
		Expiration_time: expiration,
		Timestamp:       time.Now().Unix(),
	}
	var ok1, holder = set_ex_bucket(z.table, name, bucket)
	if !ok1 {
		var owner = find_owner_of_pool(z, holder)
		var err1 = &proxy_exc{
			"",
			u.Uid,
			http_409_conflict,
			message_409_bucket_already_taken,
			map[string]string{
				"owner": owner,
			},
		}
		return_reg_error_response(z, w, r, err1)
		return nil
	}

	// Ask to make a bucket in the backend.

	//if !conf.Postpone_probe_access {}
	var err2 = probe_access_mux(z.table, pool)
	if err2 != nil {
		// (An error is already logged).
		var ok2 = delete_bucket_checking(z.table, name)
		if !ok2 {
			slogger.Error("Reg: Deleting a bucket failed (ignored)",
				"pool", pool, "bucket", name)
		}

		var err3, ok3 = err2.(*proxy_exc)
		if ok3 {
			err3.uid = u.Uid
			return_reg_error_response(z, w, r, err3)
			return nil
		} else {
			var reason = err2.Error()
			var err4 = &proxy_exc{
				"",
				u.Uid,
				http_502_bad_gateway,
				message_502_bucket_creation_failed,
				map[string]string{
					"err": reason,
				},
			}
			return_reg_error_response(z, w, r, err4)
			return nil
		}
	}

	var rspn = return_pool_prop(z, w, r, u, pool)
	return rspn
}

func delete_bucket_and_return_response(z *registrar, w http.ResponseWriter, r *http.Request, pool string, bucket string) *ui_pool_prop_response {
	var opr = "delete-bucket"

	var u = check_user_access_with_error_return(z, w, r, pool, false)
	if u == nil {
		return nil
	}
	if !check_bucket_owner_with_error_return(z, w, r, u, pool, bucket, opr) {
		return nil
	}
	if !check_empty_arguments_with_error_return(z, w, r, u, pool, opr) {
		return nil
	}

	var ok1 = delete_bucket_checking(z.table, bucket)
	if !ok1 {
		slogger.Error("Reg: Deleting a bucket failed (ignored)",
			"pool", pool, "bucket", bucket)
		var err1 = &proxy_exc{
			"",
			u.Uid,
			http_404_not_found,
			message_404_no_bucket,
			map[string]string{
				"bucket": bucket,
			},
		}
		return_reg_error_response(z, w, r, err1)
		return nil
	}

	var rspn = return_pool_prop(z, w, r, u, pool)
	return rspn
}

func make_secret_and_return_response(z *registrar, w http.ResponseWriter, r *http.Request, pool string) *ui_pool_prop_response {
	var opr = "make-secret"

	var u = check_user_access_with_error_return(z, w, r, pool, false)
	if u == nil {
		return nil
	}

	var args make_secret_request
	if !decode_request_body_with_error_return(z, w, r, u, pool, opr,
		&args, check_make_secret_request) {
		return nil
	}
	var policy = intern_secret_policy_from_ui[args.Secret_policy]
	// (Arguments are checked above).
	assert_fatal(policy != "")
	var expiration = args.Expiration_time

	var secret = &secret_record{
		Pool:            pool,
		Access_key:      "",
		Secret_key:      generate_secret_key(),
		Secret_policy:   policy,
		Expiration_time: expiration,
		Timestamp:       time.Now().Unix(),
	}
	var _ = set_with_unique_secret_key(z.table, secret)

	var rspn = return_pool_prop(z, w, r, u, pool)
	return rspn
}

func delete_secret_and_return_response(z *registrar, w http.ResponseWriter, r *http.Request, pool string, secret string) *ui_pool_prop_response {
	var opr = "delete-secret"

	var u = check_user_access_with_error_return(z, w, r, pool, false)
	if u == nil {
		return nil
	}
	if !check_secret_owner_with_error_return(z, w, r, u, pool, secret, opr) {
		return nil
	}
	if !check_empty_arguments_with_error_return(z, w, r, u, pool, opr) {
		return nil
	}

	//ensure_secret_owner_only(self.tables, access_key, pool_id)
	var ok = delete_secret_key_checking(z.table, secret)
	if !ok {
		slogger.Info("Reg: delete_secret_key() failed (ignored)")
		var err1 = &proxy_exc{
			"",
			u.Uid,
			http_404_not_found,
			message_404_bad_secret,
			map[string]string{
				"secret": secret,
			},
		}
		return_reg_error_response(z, w, r, err1)
		return nil
	}

	var rspn = return_pool_prop(z, w, r, u, pool)
	return rspn
}

// RETURN_POOL_PROP returns pool data.
func return_pool_prop(z *registrar, w http.ResponseWriter, r *http.Request, u *user_record, pool string) *ui_pool_prop_response {
	var d = gather_pool_prop(z.table, pool)
	if d == nil {
		// (This inconsistency error has been already logged).
		var err1 = &proxy_exc{
			"",
			u.Uid,
			http_500_internal_server_error,
			message_500_bad_pool_state,
			map[string]string{
				"pool": pool,
			},
		}
		return_reg_error_response(z, w, r, err1)
		return nil
	}

	var poolprop = copy_pool_prop_to_ui(d)
	var rspn = &ui_pool_prop_response{
		ui_success_response: ui_success_response{
			Status:    status_success,
			Timestamp: time.Now().Unix(),
		},
		Pool_prop: poolprop,
	}
	return_success_repsonse(z, w, r, u, rspn)
	return rspn
}

// CHECK_USER_ACCESS_WITH_ERROR_RETURN checks an access to a pool by a
// user is granted.  It returns a user record, or nil.  It is normal
// to call it without a pool (pool="") when creating a pool.
func check_user_access_with_error_return(z *registrar, w http.ResponseWriter, r *http.Request, pool string, firstsession bool) *user_record {
	//var conf = &z.conf.Registrar

	//fmt.Println(";; r.RemoteAddr=", r.RemoteAddr)
	//fmt.Println(";; X-Remote-User=", r.Header.Get("X-Remote-User"))
	//fmt.Println(";; X-Csrf-Token=", r.Header.Get("X-Csrf-Token"))

	var x_remote_user = r.Header.Get("X-Remote-User")

	// Check if Lens3 is working.

	if !check_lens3_is_running(z.table) {
		slogger.Error("Reg: Lens3 is not running")
		var err1 = &proxy_exc{
			"",
			x_remote_user,
			http_500_internal_server_error,
			message_500_lens3_not_running,
			nil,
		}
		return_reg_error_response(z, w, r, err1)
		return nil
	}

	// Check the frontend proxy.

	//var client = r.Header.Get("X-Real-Ip")
	var peer = r.RemoteAddr
	if !check_frontend_proxy_trusted(z.trusted_proxies, peer) {
		slogger.Error("Reg: Frontend proxy is untrusted", "ep", peer)
		var err2 = &proxy_exc{
			"",
			x_remote_user,
			http_500_internal_server_error,
			message_500_proxy_untrusted,
			nil,
		}
		return_reg_error_response(z, w, r, err2)
		return nil
	}

	// Check the user.

	var uid = convert_claim_to_uid(z, x_remote_user)
	var u = check_user_account(z, uid, firstsession)
	if u == nil {
		var xuid string = ITE(uid != "", uid, x_remote_user)
		slogger.Warn("Reg: User is not active", "uid", xuid)
		var err3 = &proxy_exc{
			"",
			xuid,
			http_401_unauthorized,
			message_401_bad_user_account,
			nil,
		}
		return_reg_error_response(z, w, r, err3)
		return nil
	}

	if !firstsession {
		var ok = check_csrf_tokens(z, w, r, uid)
		if !ok {
			slogger.Warn("Reg: Bad csrf tokens", "uid", uid)
			var err4 = &proxy_exc{
				"",
				u.Uid,
				http_401_unauthorized,
				message_401_bad_csrf_tokens,
				nil,
			}
			return_reg_error_response(z, w, r, err4)
			return nil
		}
	}

	if pool == "" {
		return u
	}

	// Check the pool given.  A FAILURE OF CHECKS MEANS SOMEONE FORGES
	// A REQUEST.

	if !check_pool_naming(pool) {
		slogger.Error("Reg: Bad pool name", "uid", uid, "pool", pool)
		var err5 = &proxy_exc{
			"",
			u.Uid,
			http_400_bad_request,
			message_400_no_pool,
			map[string]string{
				"pool": pool,
			},
		}
		return_reg_error_response(z, w, r, err5)
		return nil
	}

	var pooldata = get_pool(z.table, pool)
	if pooldata == nil {
		slogger.Error("Reg: No pool", "uid", uid, "pool", pool)
		var err6 = &proxy_exc{
			"",
			u.Uid,
			http_404_not_found,
			message_404_no_pool,
			map[string]string{
				"pool": pool,
			},
		}
		return_reg_error_response(z, w, r, err6)
		return nil
	}

	if pooldata.Owner_uid != u.Uid {
		slogger.Error("Reg: Not pool owner",
			"uid", uid, "pool", pool)
		var err7 = &proxy_exc{
			"",
			u.Uid,
			http_403_forbidden,
			message_403_no_pool,
			map[string]string{
				"pool": pool,
			},
		}
		return_reg_error_response(z, w, r, err7)
		return nil
	}

	if false {
		var state1, reason1 = check_pool_is_usable(z.table, pooldata)
		switch state1 {
		case pool_state_INITIAL, pool_state_READY:
			// Okay.
		case pool_state_SUSPENDED:
			// (NEVER).
		case pool_state_DISABLED, pool_state_INOPERABLE:
			slogger.Debug("Reg: Bad pool state", "pool", pool,
				"state", state1, "reason", reason1)
			var err8 = &proxy_exc{
				"",
				u.Uid,
				http_403_forbidden,
				message_403_bad_pool_state,
				map[string]string{
					"pool":   pool,
					"state":  string(state1),
					"reason": string(reason1),
				},
			}
			return_reg_error_response(z, w, r, err8)
			return nil
		default:
			panic(nil)
		}
	}

	if false {
		var state2, reason2 = check_pool_is_suspened(z.table, pool)
		switch state2 {
		case pool_state_INITIAL, pool_state_READY:
			// Okay.
		case pool_state_DISABLED:
			// Okay.
		case pool_state_SUSPENDED:
			slogger.Debug("Reg: Bad pool state", "pool", pool,
				"state", state2, "reason", reason2)
			var err9 = &proxy_exc{
				"",
				u.Uid,
				http_503_service_unavailable,
				message_503_pool_suspended,
				nil,
			}
			return_reg_error_response(z, w, r, err9)
			return nil
		case pool_state_INOPERABLE:
			var err10 = &proxy_exc{
				"",
				u.Uid,
				http_500_internal_server_error,
				message_500_bad_db_entry,
				nil,
			}
			return_reg_error_response(z, w, r, err10)
			return nil
		default:
			panic(nil)
		}
	}

	return u
}

// CHECK_LENS3_IS_RUNNING checks if any Muxs are running.
func check_lens3_is_running(t *keyval_table) bool {
	var muxs = list_mux_eps(t)
	return len(muxs) > 0
}

// CHECK_USER_ACCOUNT checks the user account is active.  It may
// register a new user record, when it is the first session under
// default-allow setting (that is, conf.User_approval=allow).  It
// deals with an erroneous uid="" but returns nil.
func check_user_account(z *registrar, uid string, firstsession bool) *user_record {
	var conf = &z.conf.Registrar

	if uid == "" {
		return nil
	}

	// Reject unregistered users.

	var approving = (conf.User_approval == user_default_allow && firstsession)
	var u1 = get_user(z.table, uid)
	if u1 == nil && !approving {
		return nil
	}

	// Reject users without local accounts.  It is weird as an
	// authenticated user doesn't have a local account.

	var _, err1 = user.Lookup(uid)
	if err1 != nil {
		// (err1 : user/UnknownUserError).
		slogger.Error("Reg: user/Lookup() errs", "uid", uid, "err", err1)
		return nil
	}

	// Approve a new user by registering.

	if u1 == nil {
		assert_fatal(approving)
		var u2 = enroll_new_user(z, uid, firstsession)
		return u2
	}

	// Check if the user is enabled.

	assert_fatal(u1 != nil)
	if !u1.Enabled {
		return nil
	}
	if !u1.Ephemeral {
		var expiration = time.Unix(u1.Expiration_time, 0)
		if !time.Now().Before(expiration) {
			return nil
		}
		return u1
	} else {
		extend_user_expiration_time(z, u1)
		return u1
	}
}

// ENROLL_NEW_USER registers a user at an access to Registrar.  It
// adds a user record with Ephemeral=true.  It checks the existence of
// the unix account.  The new record has empty groups.  It doesn't
// care races in adding a new record.
func enroll_new_user(z *registrar, uid string, firstsession bool) *user_record {
	var conf = &z.conf.Registrar
	var approving = (conf.User_approval == user_default_allow && firstsession)
	assert_fatal(approving)

	if conf.Claim_uid_map == claim_uid_map_map {
		slogger.Error("Reg: Configuration error",
			"user_approval", conf.User_approval,
			"claim_uid_map", conf.Claim_uid_map)
		return nil
	}

	var uu, err1 = user.Lookup(uid)
	if err1 != nil {
		// (err1 : user.UnknownUserError)
		slogger.Error("Reg: user/Lookup() failed", "uid", uid, "err", err1)
		return nil
	}

	var uid_n, err2 = strconv.Atoi(uu.Uid)
	if err2 != nil {
		slogger.Error("Reg: user/Lookup() returns non-numeric uid",
			"uid", uid, "user.User.Uid", uu.Uid)
		return nil
	}
	if len(conf.Uid_allow_range_list) != 0 {
		if !check_int_in_ranges(conf.Uid_allow_range_list, uid_n) {
			slogger.Info("Reg: A new user blocked", "uid", uid)
			return nil
		}
	}
	if check_int_in_ranges(conf.Uid_block_range_list, uid_n) {
		slogger.Info("Reg: A new user blocked", "uid", uid)
		return nil
	}

	var groups = list_groups_of_user(z, uid)

	if len(groups) == 0 {
		slogger.Info("Reg: No groups for a new user", "uid", uid)
		return nil
	}

	slogger.Warn("Reg: Enroll a user automatically", "uid", uid)

	assert_fatal(conf.User_expiration_days > 0)
	var days = conf.User_expiration_days.time_duration()
	var expiration = time.Now().Add(days).Unix()
	var now int64 = time.Now().Unix()
	var newuser = &user_record{
		Uid:                        uid,
		Claim:                      "",
		Groups:                     []string{},
		Enabled:                    true,
		Ephemeral:                  true,
		Expiration_time:            expiration,
		Check_terms_and_conditions: false,
		Timestamp:                  now,
	}
	set_user_raw(z.table, newuser)
	return newuser
}

func check_csrf_tokens(z *registrar, w http.ResponseWriter, r *http.Request, uid string) bool {
	var v *csrf_token_record = get_csrf_token(z.table, uid)
	var c, _ = r.Cookie("fastapi-csrf-token")
	var h = r.Header.Get("X-Csrf-Token")
	var ok = (v != nil && c != nil && h != "" &&
		v.Csrf_token[0] == c.Value && v.Csrf_token[1] == h)
	if !ok {
		slogger.Debug("Reg: Checking csrf-tokens failed",
			"uid", uid, "token", v.Csrf_token, "header", h, "cookie", c)
	}
	return ok
}

func make_csrf_tokens(z *registrar, uid string) *csrf_token_record {
	var conf = &z.conf.Registrar
	var now = time.Now().Unix()
	var data = &csrf_token_record{
		Csrf_token: []string{
			generate_random_key(),
			generate_random_key(),
		},
		Timestamp: now,
	}
	var expiry = (conf.Ui_session_duration).time_duration()
	set_csrf_token(z.table, uid, data)
	var ok = set_csrf_token_expiry(z.table, uid, expiry)
	if !ok {
		// Ignore an error.
		slogger.Error("Reg: DB.Expire(csrf-token-record) failed",
			"uid", uid)
	}
	//var x = get_csrf_token(z.table, uid)
	//fmt.Println("make_csrf_tokens=", x)
	return data
}

// CHECK_MAKE_POOL_REQUEST checks the entires of bucket-directory
// and owner-gid.  It normalizes the path of a bucket-directory in
// the posix sense.
func check_make_pool_request(z *registrar, u *user_record, pool string, data any) *reg_bad_argument_message {
	var args, ok = data.(*make_pool_request)
	assert_fatal(ok)

	// Check bucket-directory path.

	var bd = args.Bucket_directory
	var path = filepath.Clean(bd)
	if !filepath.IsAbs(path) {
		return &reg_bad_argument_message{
			message_400_bad_bucket_directory,
			map[string]string{
				"path": bd,
			},
		}
	}
	args.Bucket_directory = path

	// Check GID.  UID is not in the arguments.

	var groups []string
	if !u.Ephemeral {
		groups = u.Groups
	} else {
		groups = list_groups_of_user(z, u.Uid)
	}

	var gid = args.Owner_gid
	if slices.Index(groups, gid) == -1 {
		return &reg_bad_argument_message{
			message_400_bad_group,
			map[string]string{
				"group": gid,
			},
		}
	}
	return nil
}

func check_make_bucket_request(z *registrar, u *user_record, pool string, data any) *reg_bad_argument_message {
	var args, ok1 = data.(*make_bucket_request)
	assert_fatal(ok1)

	// Check Bucket.
	if !check_bucket_naming(args.Bucket) {
		return &reg_bad_argument_message{
			message_400_bad_bucket,
			map[string]string{
				"bucket": args.Bucket,
			},
		}
	}
	// Check Bucket_policy.
	var _, ok2 = intern_bucket_policy_from_ui[args.Bucket_policy]
	//if slices.Index(bucket_policy_ui_list, args.Bucket_policy) == -1 {
	if !ok2 {
		return &reg_bad_argument_message{
			message_400_bad_policy,
			map[string]string{
				"policy": args.Bucket_policy,
			},
		}
	}
	return nil
}

func check_make_secret_request(z *registrar, u *user_record, pool string, data any) *reg_bad_argument_message {
	var args, ok1 = data.(*make_secret_request)
	assert_fatal(ok1)

	// Check Secret_policy.
	var _, ok2 = intern_secret_policy_from_ui[args.Secret_policy]
	//if slices.Index(secret_policy_ui_list, args.Secret_policy) == -1
	if !ok2 {
		return &reg_bad_argument_message{
			message_400_bad_policy,
			map[string]string{
				"policy": args.Secret_policy,
			},
		}
	}
	// Check Expiration_time.
	var conf = &z.conf.Registrar
	assert_fatal(conf.Secret_expiration_days > 0)
	var days = conf.Secret_expiration_days.time_duration()
	var e = time.Unix(args.Expiration_time, 0)
	var now = time.Now()
	if !(now.AddDate(0, 0, -1).Before(e) && e.Before(now.Add(days))) {
		return &reg_bad_argument_message{
			message_400_bad_expiration,
			map[string]string{
				"expiration": e.Format(time.DateOnly),
			},
		}
	}
	return nil
}

func check_empty_arguments_with_error_return(z *registrar, w http.ResponseWriter, r *http.Request, u *user_record, pool string, opr string) bool {
	var is = r.Body
	var err1 = check_stream_eof(is, true)
	if err1 != nil {
		slogger.Info("Reg: Garbage in an empty request body",
			"err", err1)
		var err2 = &proxy_exc{
			"",
			u.Uid,
			http_400_bad_request,
			message_400_arguments_not_empty,
			nil,
		}
		return_reg_error_response(z, w, r, err2)
		return false
	}
	return true
}

func check_bucket_owner_with_error_return(z *registrar, w http.ResponseWriter, r *http.Request, u *user_record, pool string, bucket string, opr string) bool {
	if !check_bucket_naming_with_error_return(z, w, r, u, bucket) {
		return false
	}
	var b *bucket_record = get_bucket(z.table, bucket)
	if b == nil {
		var err1 = &proxy_exc{
			"",
			u.Uid,
			http_404_not_found,
			message_404_no_bucket,
			map[string]string{
				"bucket": bucket,
			},
		}
		return_reg_error_response(z, w, r, err1)
		return false
	}
	if b.Pool != pool {
		var err2 = &proxy_exc{
			"",
			u.Uid,
			http_403_forbidden,
			message_403_not_bucket_owner,
			map[string]string{
				"bucket": bucket,
			},
		}
		return_reg_error_response(z, w, r, err2)
		return false
	}
	return true
}

func check_bucket_naming_with_error_return(z *registrar, w http.ResponseWriter, r *http.Request, u *user_record, bucket string) bool {
	var ok = check_bucket_naming(bucket)
	if !ok {
		var err1 = &proxy_exc{
			"",
			u.Uid,
			http_400_bad_request,
			message_400_bad_bucket,
			map[string]string{
				"bucket": bucket,
			},
		}
		return_reg_error_response(z, w, r, err1)
	}
	return ok
}

func check_secret_owner_with_error_return(z *registrar, w http.ResponseWriter, r *http.Request, u *user_record, pool string, secret string, opr string) bool {
	if !check_secret_naming_with_error_return(z, w, r, u, secret) {
		return false
	}
	var b *secret_record = get_secret(z.table, secret)
	if b == nil {
		var err1 = &proxy_exc{
			"",
			u.Uid,
			http_404_not_found,
			message_404_no_secret,
			map[string]string{
				"secret": secret,
			},
		}
		return_reg_error_response(z, w, r, err1)
		return false
	}
	if b.Pool != pool {
		var err2 = &proxy_exc{
			"",
			u.Uid,
			http_403_forbidden,
			message_403_not_secret_owner,
			map[string]string{
				"secret": secret,
			},
		}
		return_reg_error_response(z, w, r, err2)
		return false
	}
	return true
}

func check_secret_naming_with_error_return(z *registrar, w http.ResponseWriter, r *http.Request, u *user_record, secret string) bool {
	var ok = check_secret_naming(secret)
	if !ok {
		var err1 = &proxy_exc{
			"",
			u.Uid,
			http_400_bad_request,
			message_400_bad_secret,
			map[string]string{
				"secret": secret,
			},
		}
		return_reg_error_response(z, w, r, err1)
	}
	return ok
}

type checker_fn func(z *registrar, u *user_record, pool string, data any) *reg_bad_argument_message

// DECODE_REQUEST_BODY_WITH_ERROR_RETURN reads the body into the data.
// It return true if decoding succeeds.  Any garbage after json data
// is an error.
func decode_request_body_with_error_return(z *registrar, w http.ResponseWriter, r *http.Request, u *user_record, pool string, opr string, data any, check checker_fn) bool {
	var ok1 = decode_request_body(z, r, data)
	if !ok1 {
		var err1 = &proxy_exc{
			"",
			u.Uid,
			http_400_bad_request,
			message_400_bad_body_encoding,
			map[string]string{
				"op": opr,
			},
		}
		return_reg_error_response(z, w, r, err1)
		return false
	}
	var msg = check(z, u, pool, data)
	if msg != nil {
		var err2 = &proxy_exc{
			"",
			u.Uid,
			http_400_bad_request,
			msg.error,
			msg.info,
		}
		return_reg_error_response(z, w, r, err2)
		return false
	}
	return true
}

func decode_request_body(z *registrar, r *http.Request, data any) bool {
	// r.Body : io.ReadCloser.
	var d = json.NewDecoder(r.Body)
	d.DisallowUnknownFields()
	var err1 = d.Decode(data)
	if err1 != nil {
		slogger.Debug("Reg: Error in reading request body", "err", err1)
		return false
	}
	if !check_fields_filled(data) {
		slogger.Debug("Reg: Unfilled fields in request body",
			"data", data)
		return false
	}
	// Check EOF.  Garbage data means an error.
	var is = d.Buffered()
	var err2 = check_stream_eof(is, false)
	if err2 != nil {
		slogger.Info("Reg: Garbage after json data in request body",
			"err", err2)
	}
	return (err2 == nil)
}

// CONVERT_CLAIM_TO_UID converts a name (x_remote_user) to an uid.  It
// returns "" on errors.
func convert_claim_to_uid(z *registrar, x_remote_user string) string {
	var conf = &z.conf.Registrar
	switch conf.Claim_uid_map {
	case claim_uid_map_id:
		return x_remote_user
	case claim_uid_map_email_name:
		var v = strings.Split(x_remote_user, "@")
		if len(v) != 2 {
			return ""
		}
		return v[0]
	case claim_uid_map_map:
		var x *user_claim_record = get_user_claim(z.table, x_remote_user)
		if x == nil {
			return ""
		}
		return x.Uid
	default:
		panic(nil)
	}
}

func copy_user_record_to_ui(z *registrar, u *user_record, groups []string) *user_info_ui {
	var v = &user_info_ui{
		Api_version:   reg_api_version,
		Uid:           u.Uid,
		Groups:        groups,
		Lens3_version: lens3_version,
		S3_url:        z.conf.UI.S3_url,
		Footer_banner: z.conf.UI.Footer_banner,
	}
	return v
}

func copy_pool_prop_to_ui(d *pool_prop) *pool_prop_ui {
	var v = &pool_prop_ui{
		// POOL_RECORD
		Pool:             d.pool_record.Pool,
		Bucket_directory: d.Bucket_directory,
		Owner_uid:        d.Owner_uid,
		Owner_gid:        d.Owner_gid,
		Probe_key:        d.Probe_key,
		Online_status:    d.pool_record.Enabled,
		Expiration_time:  d.pool_record.Expiration_time,
		Timestamp:        d.pool_record.Timestamp,
		// POOL_PROP
		Buckets: copy_bucket_data_to_ui(d.Buckets),
		Secrets: copy_secret_data_to_ui(d.Secrets),
		// USER_RECORD
		User_enabled_status: d.user_record.Enabled,
		// POOL_STATE_RECORD
		Backend_state:  d.blurred_state_record.State,
		Backend_reason: d.blurred_state_record.Reason,
	}
	return v
}

func copy_bucket_data_to_ui(m []*bucket_record) []*bucket_data_ui {
	var buckets []*bucket_data_ui = make([]*bucket_data_ui, 0)
	for _, d := range m {
		var u = &bucket_data_ui{
			Pool:          d.Pool,
			Bucket:        d.Bucket,
			Bucket_policy: export_bucket_policy_to_ui[d.Bucket_policy],
			Timestamp:     d.Timestamp,
		}
		buckets = append(buckets, u)
	}
	return buckets
}

func copy_secret_data_to_ui(m []*secret_record) []*secret_data_ui {
	var secrets []*secret_data_ui = make([]*secret_data_ui, 0)
	for _, d := range m {
		if d.Secret_policy == secret_policy_internal_access {
			continue
		}
		var u = &secret_data_ui{
			Pool:            d.Pool,
			Access_key:      d.Access_key,
			Secret_key:      d.Secret_key,
			Secret_policy:   export_secret_policy_to_ui[d.Secret_policy],
			Expiration_time: d.Expiration_time,
			Timestamp:       d.Timestamp,
		}
		secrets = append(secrets, u)
	}
	return secrets
}

// FIND_OWNER_OF_POOL finds an owner of a pool for printing error
// messages.  It returns the string "unknown-user", when an owner is
// not found.
func find_owner_of_pool(z *registrar, pool string) string {
	if pool == "" {
		return "unknown-user"
	}
	var pooldata = get_pool(z.table, pool)
	if pooldata == nil {
		return "unknown-user"
	}
	return pooldata.Owner_uid
}

// EXTEND_USER_EXPIRATION_TIME extends user's validity by the
// specified days.
func extend_user_expiration_time(z *registrar, u *user_record) {
	var conf = &z.conf.Registrar
	assert_fatal(conf.User_expiration_days > 0)
	var old_expiration = time.Unix(u.Expiration_time, 0)
	var days = conf.User_expiration_days.time_duration()
	var new_expiration = time.Now().Add(days)
	if old_expiration.Before(new_expiration) {
		u.Expiration_time = new_expiration.Unix()
		set_user_raw(z.table, u)
	}
}

func list_groups_of_user(z *registrar, uid string) []string {
	var conf = &z.conf.Registrar

	var uu, err1 = user.Lookup(uid)
	if err1 != nil {
		// (err1 : user.UnknownUserError)
		slogger.Error("Reg: user/Lookup() failed", "uid", uid, "err", err1)
		return nil
	}
	var gids, err2 = uu.GroupIds()
	if err2 != nil {
		slogger.Error("Reg: user/User.GroupIds() failed",
			"uid", uid, "err", err2)
		return nil
	}
	var groups []string
	for _, g1 := range gids {
		var gid_n, err3 = strconv.Atoi(g1)
		if err3 != nil {
			slogger.Error("Reg: user/User.GroupIds() returns non-numeric gid",
				"uid", uid, "gid", g1)
			continue
		}
		if check_int_in_ranges(conf.Gid_drop_range_list, gid_n) {
			continue
		}
		if slices.Index(conf.Gid_drop_list, gid_n) != -1 {
			continue
		}
		var gr, err4 = user.LookupGroupId(g1)
		if err4 != nil {
			slogger.Error("Reg(0 user/LookupGroupId() failed",
				"gid", g1, "err", err4)
			continue
		}
		groups = append(groups, gr.Name)
	}
	return groups
}

// LIST_POOLS_OF_USER returns a list of pools that are owned by a
// specified user.
func list_pools_of_user(t *keyval_table, uid string) []string {
	var namelist = list_pools(t, "*")
	var list []string
	for _, pool := range namelist {
		var p = get_pool(t, pool)
		if p != nil && p.Owner_uid == uid {
			list = append(list, pool)
		}
	}
	return list
}

// DEREGISTER_USER deletes a user, along with the pools owned by the
// user.
func deregister_user(t *keyval_table, uid string) {
	var poolnames = list_pools_of_user(t, uid)
	for _, pool := range poolnames {
		// Ignore errors.
		var _ = deregister_pool(t, pool)
	}
	clear_user_claim(t, uid)
	delete_user_timestamp(t, uid)
	delete_user(t, uid)
}

// DEREGISTER_POOL deletes a pool, along with its members, i.e.,
// bucket-directory, buckets, access keys, and its state recored.  It
// returns OK/NG.  It ignores most of the errors but only fails when a
// pool is not found.  It does nothing to do with the backend.  That
// is, it does not remove or disable buckets in the backend.
func deregister_pool(t *keyval_table, pool string) bool {
	var prop = gather_pool_prop(t, pool)
	if prop == nil {
		slogger.Error("Reg: Deleting a non-existing pool", "pool", pool)
		return false
	}
	var ok = deregister_pool_by_prop(t, prop)
	return ok
}

func deregister_pool_by_prop(t *keyval_table, prop *pool_prop) bool {
	var pool = prop.pool_record.Pool

	// Delete bucket-directory.

	if prop.Bucket_directory != "" {
		var path = prop.Bucket_directory
		var ok1 = delete_bucket_directory_checking(t, path)
		if !ok1 {
			slogger.Error("Reg: Deleting a bucket-directory failed (ignored)",
				"pool", pool, "path", path)
		}
	}

	// Delete buckets.

	for _, b := range prop.Buckets {
		assert_fatal(b.Pool == pool)
		var ok2 = delete_bucket_checking(t, b.Bucket)
		if !ok2 {
			slogger.Error("Reg: Deleting a bucket failed (ignored)",
				"pool", pool, "bucket", b.Bucket)
		}
	}

	// Delete access keys.

	for _, k := range prop.Secrets {
		assert_fatal(k.Pool == pool)
		var ok3 = delete_secret_key_checking(t, k.Access_key)
		if !ok3 {
			slogger.Error("Reg: Deleting an access-key failed (ignored)",
				"pool", pool, "secret", k.Access_key)
		}
	}

	delete_blurred_state(t, pool)
	delete_pool_timestamp(t, pool)
	delete_pool(t, pool)

	var ok4 = delete_pool_name_checking(t, pool)
	if !ok4 {
		slogger.Error("Reg: Deleting a pool entry failed (ignored)",
			"pool", pool)
	}

	return true
}

// RETURN_SUCCESS_REPSONSE returns a success response (200).  NOTE: It is
// not possible to obtain a response object from http.ResponseWriter.
// http.ResponseWriter is an instance of http.response, but it is not
// public.  Also, the field http.Request.Response is null.  Niether, a
// context does not have a response.  http.RoundTrip is on the client
// side.
func return_success_repsonse(z *registrar, w http.ResponseWriter, rqst *http.Request, u *user_record, value any) {
	assert_fatal(u != nil)
	var v1, err1 = json.Marshal(value)
	if err1 != nil {
		slogger.Error("Reg: json/Marshal() failed", "err", err1)
		panic(nil)
	}

	if false {
		fmt.Printf("*** Response=%#v\n", string(v1))
	}

	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	var _, err2 = w.Write(v1)
	if err2 != nil {
		slogger.Error("Reg: Writing reply failed", "err", err2)
	}
	var wf, ok = w.(http.Flusher)
	if ok {
		wf.Flush()
	}
	log_reg_access_by_request(rqst, 200, int64(len(v1)), u.Uid, "")
	return
}

func return_reg_error_response(z *registrar, w http.ResponseWriter, rqst *http.Request, err *proxy_exc) {
	var delay_ms = z.conf.Registrar.Error_response_delay_ms
	var logprefix = "Reg: "
	var logfn = log_reg_access_by_request
	return_error_response(w, rqst, err, delay_ms, logprefix, logfn)
}

// PROBE_ACCESS_MUX accesses a Multiplexer using a probe-key from
// Registrar.  A probe-access tries to make buckets absent in the
// backend.  It uses a probe-key and it is ignored by a Multiplexer.
// Region and timeout used is fairly arbitrary.  Decoding a response
// with "ui_error_response" works both successful or failure cases.
func probe_access_mux(t *keyval_table, pool string) error {
	var pooldata = get_pool(t, pool)
	if pooldata == nil {
		var err1 = fmt.Errorf("Pool not found: pool=%q", pool)
		slogger.Error("Reg: Probe-access failed", "pool", pool, "err", err1)
		panic(nil)
	}
	var secret = get_secret(t, pooldata.Probe_key)
	if secret == nil {
		var err2 = fmt.Errorf("Probe-key not found: pool=%q", pool)
		slogger.Error("Reg: Probe-access failed", "pool", pool, "err", err2)
		panic(nil)
	}

	var ep string
	var be1 = get_backend(t, pool)
	if be1 != nil {
		ep = be1.Mux_ep
	} else {
		var eps []*mux_record = list_mux_eps(t)
		if len(eps) == 0 {
			var err3 = fmt.Errorf("No Multiplexers")
			slogger.Error("Reg: Probe-access failed", "pool", pool, "err", err3)
			return err3
		}
		var i = rand.IntN(len(eps))
		ep = eps[i].Mux_ep
	}

	var timeout = time.Duration(60000 * time.Millisecond)
	var ctx, cancel = context.WithTimeout(context.Background(), timeout)
	defer cancel()
	var url1 = ("http://" + ep)

	// (Use nil:io.Reader for empty body).
	var r, err4 = http.NewRequestWithContext(ctx, http.MethodGet, url1, nil)
	if err4 != nil {
		slogger.Error("Reg: Probe-access failed",
			"pool", pool, "op", "http/Client.NewRequest()", "err", err4)
		return err4
	}

	var hash = empty_payload_hash_sha256
	r.Header.Set("X-Amz-Content-Sha256", hash)
	var dummy = &backend_record{
		Backend_ep:  ep,
		Root_access: secret.Access_key,
		Root_secret: secret.Secret_key,
	}
	var err5 = sign_by_backend_credential(r, dummy)
	if err5 != nil {
		slogger.Error("Reg: Probe-access failed",
			"pool", pool, "op", "signer/Signer.SignHTTP()", "err", err5)
		return err5
	}

	var c = &http.Client{
		Timeout: timeout,
	}
	var rspn, err6 = c.Do(r)
	if err6 != nil {
		slogger.Error("Reg: Probe-access failed",
			"pool", pool, "op", "http/Client.Do()", "err", err6)
		return err6
	}
	defer rspn.Body.Close()

	var data ui_error_response
	var d = json.NewDecoder(rspn.Body)
	//d.DisallowUnknownFields()
	var err7 = d.Decode(&data)
	if err7 != nil {
		slogger.Error("Reg: Probe-access failed",
			"pool", pool, "op", "json/Decoder.Decode()", "err", err7)
		return err7
	}

	if rspn.StatusCode == http.StatusOK {
		return nil
	} else {
		var err8 = &proxy_exc{
			"",
			"",
			rspn.StatusCode,
			data.Reason.Error,
			data.Reason.Info,
		}
		slogger.Debug("Reg: Probe-access failed",
			"pool", pool, "err", err8)
		return err8
	}
}
