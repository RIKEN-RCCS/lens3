/* Lens3-Reg.  Registrar of buckets and secrets via a Web-API. */

// Copyright 2022-2024 RIKEN R-CCS
// SPDX-License-Identifier: BSD-2-Clause

package lens3

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

// Registrar uses a "double submit cookie" for CSRF prevention used in
// fastapi_csrf_protect.  It uses a cookie+header pair.  A cookie is
// "fastapi-csrf-token" and a header is "X-Csrf-Token".  The CSRF
// state of a client is set by a response of "GET /user_info".
// (However, this implementes only the header part, assuming the
// cookie part is subsumed by authenitication by httpd).  See
// https://github.com/aekasitt/fastapi-csrf-protect

// NOTE???: Maybe, consider adding a "Retry-After" header for 503
// error.

import (
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net"
	"net/http"
	"os/user"
	"path/filepath"
	"slices"
	"strconv"
	"strings"
	"sync"
	"time"
	//"context"
	//"flag"
	//"log"
	//"maps"
	//"math/rand/v2"
	//"net/http/httputil"
	//"net/url"
	//"os"
	//"runtime"
	//"runtime"
	//"runtime/debug"
)

// UI script is by Golang's embedded files.

import "embed"

//go:embed ui
var efs1 embed.FS

//go:embed ui2
var efs2 embed.FS

type registrar struct {
	// EP_PORT is a listening port of Registrar (":port").
	ep_port string

	verbose bool

	table *keyval_table

	trusted_proxies []net.IP

	// CH_QUIT is to receive quitting notification.
	ch_quit_service <-chan vacuous

	server *http.Server

	mqtt *mqtt_client

	conf *reg_conf
}

const reg_api_version = "v1.2"

type response_to_ui interface{ response_union() }

func (*pool_prop_response) response_union() {}
func (*user_info_response) response_union() {}

// RESPONSE is a json format of a response to UI.  See the function
// set_pool_data() in "v1/ui/src/lens3c.ts".  Status is "success" or
// "error".
type response_common struct {
	Status    string            `json:"status"`
	Reason    map[string]string `json:"reason"`
	Timestamp int64             `json:"time"`
}

type success_response struct {
	response_common
}

type error_response struct {
	response_common
}

type user_info_response struct {
	response_common
	Csrf_token string       `json:"x_csrf_token"`
	User_info  user_info_ui `json:"user_info"`
}

type pool_prop_response struct {
	response_common
	Pool_prop *pool_prop_ui `json:"pool_desc"`
}

type pool_list_response struct {
	response_common
	Pool_list []*pool_prop_ui `json:"pool_list"`
}

type pool_prop_ui struct {
	Pool                string            `json:"pool_name"`
	Buckets_directory   string            `json:"buckets_directory"`
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

type empty_request struct{}

type make_pool_arguments struct {
	Buckets_directory string `json:"buckets_directory"`
	Owner_gid         string `json:"owner_gid"`
}

type make_bucket_arguments struct {
	Bucket        string `json:"name"`
	Bucket_policy string `json:"bkt_policy"`
}

type make_secret_arguments struct {
	Secret_policy   string `json:"key_policy"`
	Expiration_time int64  `json:"expiration_time"`
}

var the_registrar = &registrar{}

var err_body_not_allowed = errors.New("http: request method or response status code does not allow body")

const (
	bucket_policy_ui_NONE string = "none"
	bucket_policy_ui_WO   string = "upload"
	bucket_policy_ui_RO   string = "download"
	bucket_policy_ui_RW   string = "public"
)

var bucket_policy_ui_list = []string{
	bucket_policy_ui_NONE,
	bucket_policy_ui_WO,
	bucket_policy_ui_RO,
	bucket_policy_ui_RW,
}

var export_bucket_policy_to_ui = map[bucket_policy]string{
	bucket_policy_NONE: bucket_policy_ui_NONE,
	bucket_policy_WO:   bucket_policy_ui_WO,
	bucket_policy_RO:   bucket_policy_ui_RO,
	bucket_policy_RW:   bucket_policy_ui_RW,
}

const (
	secret_policy_ui_RW string = "readwrite"
	secret_policy_ui_RO string = "readonly"
	secret_policy_ui_WO string = "writeonly"
)

var secret_policy_ui_list = []string{
	secret_policy_ui_RW,
	secret_policy_ui_RO,
	secret_policy_ui_WO,
}

var export_secret_policy_to_ui = map[secret_policy]string{
	secret_policy_RW: secret_policy_ui_RW,
	secret_policy_RO: secret_policy_ui_RO,
	secret_policy_WO: secret_policy_ui_WO,
}

// REG_ERROR_MESSAGE is an extra error message returned to UI on errors.
type reg_error_message [][2]string

func configure_registrar(z *registrar, t *keyval_table, qch <-chan vacuous, c *reg_conf) {
	z.table = t
	z.ch_quit_service = qch
	z.conf = c
	z.verbose = true

	var conf = &z.conf.Registrar
	open_log_for_reg(c.Log.Access_log_file)
	//z.mqtt = configure_mqtt(&c.Logging.Mqtt, qch)

	z.ep_port = net.JoinHostPort("", strconv.Itoa(conf.Port))

	var addrs []net.IP = convert_hosts_to_addrs(conf.Trusted_proxy_list)
	slogger.Debug("Reg() Trusted proxies", "ip", addrs)
	if len(addrs) == 0 {
		slogger.Error("Reg() No trusted proxies")
		panic(nil)
	}
	z.trusted_proxies = addrs
}

func start_registrar(z *registrar, wg *sync.WaitGroup) {
	slogger.Debug("Reg() start_registrar()")

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
		slogger.Debug("Reg() GET /")
		http.Redirect(w, r, "./ui/index.html", http.StatusSeeOther)
	})

	router.HandleFunc("GET /ui/index.html", func(w http.ResponseWriter, r *http.Request) {
		defer handle_registrar_exc(z, w, r)
		var _ = return_ui_script(z, w, r, "ui/index.html")
	})

	router.HandleFunc("GET /ui2/index.html", func(w http.ResponseWriter, r *http.Request) {
		defer handle_registrar_exc(z, w, r)
		var _ = return_ui_script(z, w, r, "ui2/index.html")
	})

	router.HandleFunc("GET /ui/", func(w http.ResponseWriter, r *http.Request) {
		defer handle_registrar_exc(z, w, r)
		var _ = return_file(z, w, r, r.URL.Path, &efs1)
	})

	router.HandleFunc("GET /ui2/", func(w http.ResponseWriter, r *http.Request) {
		defer handle_registrar_exc(z, w, r)
		var _ = return_file(z, w, r, r.URL.Path, &efs2)
	})

	router.HandleFunc("GET /user-info", func(w http.ResponseWriter, r *http.Request) {
		defer handle_registrar_exc(z, w, r)
		slogger.Debug("Reg() GET /user-info")
		var _ = return_user_info(z, w, r)
	})

	router.HandleFunc("GET /pool", func(w http.ResponseWriter, r *http.Request) {
		defer handle_registrar_exc(z, w, r)
		slogger.Debug("Reg() GET /pool")
		var _ = list_pool_and_return_response(z, w, r, "")
	})

	router.HandleFunc("GET /pool/{pool}", func(w http.ResponseWriter, r *http.Request) {
		defer handle_registrar_exc(z, w, r)
		var pool = r.PathValue("pool")
		slogger.Debug("Reg() GET /pool", "pool", pool)
		var _ = list_pool_and_return_response(z, w, r, pool)
	})

	// A POST request makes a pool.

	router.HandleFunc("POST /pool", func(w http.ResponseWriter, r *http.Request) {
		defer handle_registrar_exc(z, w, r)
		slogger.Debug("Reg() POST /pool")
		var _ = make_pool_and_return_response(z, w, r)
	})

	router.HandleFunc("DELETE /pool/{pool}", func(w http.ResponseWriter, r *http.Request) {
		defer handle_registrar_exc(z, w, r)
		var pool = r.PathValue("pool")
		slogger.Debug("Reg() DELETE /pool", "pool", pool)
		var _ = delete_pool_and_return_response(z, w, r, pool)
	})

	// A PUT request makes a bucket.

	router.HandleFunc("PUT /pool/{pool}/bucket", func(w http.ResponseWriter, r *http.Request) {
		defer handle_registrar_exc(z, w, r)
		var pool = r.PathValue("pool")
		slogger.Debug("Reg() PUT /pool/*/bucket", "pool", pool)
		var _ = make_bucket_and_return_response(z, w, r, pool)
	})

	router.HandleFunc("DELETE /pool/{pool}/bucket/{bucket}", func(w http.ResponseWriter, r *http.Request) {
		defer handle_registrar_exc(z, w, r)
		var pool = r.PathValue("pool")
		var bucket = r.PathValue("bucket")
		slogger.Debug("Reg() DELETE /pool/*/bucket", "pool", pool,
			"bucket", bucket)
		var _ = delete_bucket_and_return_response(z, w, r, pool, bucket)
	})

	// A POST request makes a secret.

	router.HandleFunc("POST /pool/{pool}/secret", func(w http.ResponseWriter, r *http.Request) {
		defer handle_registrar_exc(z, w, r)
		var pool = r.PathValue("pool")
		slogger.Debug("Reg() POST /pool/*/secret", "pool", pool)
		var _ = make_secret_and_return_response(z, w, r, pool)
	})

	router.HandleFunc("DELETE /pool/{pool}/secret/{secret}", func(w http.ResponseWriter, r *http.Request) {
		defer handle_registrar_exc(z, w, r)
		var pool = r.PathValue("pool")
		var secret = r.PathValue("secret")
		slogger.Debug("Reg() DELETE /pool/*/secret", "pool", pool,
			"secret", secret)
		var _ = delete_secret_and_return_response(z, w, r, pool, secret)
	})

	slogger.Info("Reg() Start Registrar", "ep", z.ep_port)
	var err1 = z.server.ListenAndServe()
	slogger.Info("Reg() http.Server.ListenAndServe() done", "err", err1)
}

func handle_registrar_exc(z *registrar, w http.ResponseWriter, rqst *http.Request) {
	var delay_ms = z.conf.Registrar.Error_response_delay_ms
	var logfn = log_reg_access_by_request
	handle_exc("Reg()", delay_ms, logfn, w, rqst)
}

func return_ui_script(z *registrar, w http.ResponseWriter, rqst *http.Request, path string) *string {
	var data1, err1 = efs1.ReadFile(path)
	if err1 != nil {
		delay_sleep(z.conf.Registrar.Error_response_delay_ms)
		var msg = "BAD"
		var code = http_500_internal_server_error
		http.Error(w, msg, code)
		//log_access_with_user(rspn, "-")
		log_reg_access_by_request(rqst, code, int64(len(msg)), "-", "-")
		return nil
	}
	var parameters = (`<script type="text/javascript">const base_path_="` +
		z.conf.Registrar.Base_path + `";</script>`)
	var data2 = strings.Replace(string(data1),
		"PLACE_BASE_PATH_SETTING_HERE", parameters, 1)
	//fmt.Println(string(data2))
	var _, err2 = io.WriteString(w, data2)
	if err2 != nil {
		slogger.Error("Reg() Writing reply failed", "err", err2)
	}
	var wf, ok = w.(http.Flusher)
	if ok {
		wf.Flush()
	}
	//log_access_with_user(rspn, "-")
	log_reg_access_by_request(rqst, 200, int64(len(data2)), "-", "-")
	return &data2
}

func return_file(z *registrar, w http.ResponseWriter, rqst *http.Request, path string, efs1 *embed.FS) *[]byte {
	var data1, err1 = efs1.ReadFile(path)
	if err1 != nil {
		delay_sleep(z.conf.Registrar.Error_response_delay_ms)
		var msg = "BAD"
		var code = http_500_internal_server_error
		http.Error(w, msg, code)
		//log_access_with_user(rspn, "-")
		log_reg_access_by_request(rqst, code, int64(len(msg)), "-", "-")
		return nil
	}
	var _, err2 = w.Write(data1)
	if err2 != nil {
		slogger.Error("Reg() Writing reply failed", "err", err2)
	}
	var wf, ok = w.(http.Flusher)
	if ok {
		wf.Flush()
	}
	//log_access_with_user(rspn, "-")
	log_reg_access_by_request(rqst, 200, int64(len(data1)), "-", "-")
	return &data1
}

// RETURN_USER_INFO returns a response for GET "/user-info".  This
// request is assumed as the first request, and it initializes the
// CSRF state.  u.Ephemeral=true means the user was added
// automatically.  It makes a list of groups each time for such a
// user, because groups may be changed.  The groups may be empty.
func return_user_info(z *registrar, w http.ResponseWriter, r *http.Request) *user_info_response {
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
	var rspn = &user_info_response{
		response_common: response_common{
			Status:    "success",
			Reason:    nil,
			Timestamp: now,
		},
		Csrf_token: csrf.Csrf_token[1],
		User_info:  *info,
	}
	return_json_repsonse(z, w, r, u, rspn)
	return rspn
}

// LIST_POOL_AND_RETURN_RESPONSE returns a record of a pool with a
// given pool-name, or a list of pools owned by a user for "".
func list_pool_and_return_response(z *registrar, w http.ResponseWriter, r *http.Request, pool string) *pool_list_response {
	var opr = "list-pool"

	var u = check_user_access_with_error_return(z, w, r, pool, false)
	if u == nil {
		return nil
	}
	if !check_empty_arguments_with_error_return(z, w, r, u, pool, opr) {
		return nil
	}

	var namelist = list_pools(z.table, ITE(pool == "", "*", pool))
	var poollist []*pool_prop_ui
	for _, name := range namelist {
		var d = gather_pool_prop(z.table, name)
		if d != nil && d.Owner_uid == u.Uid {
			poollist = append(poollist, copy_pool_prop_to_ui(d))
		}
	}

	if pool != "" && len(poollist) == 0 {
		var err1 = &proxy_exc{
			u.Uid,
			http_400_bad_request,
			[][2]string{
				message_no_pool,
				{"pool", pool},
			},
		}
		return_reg_error_response(z, w, r, u, err1)
		return nil
	}
	if pool != "" && len(poollist) > 1 {
		slogger.Error("Reg() Multiple pools with the same id", "pool", pool)
		var err2 = &proxy_exc{
			u.Uid,
			http_500_internal_server_error,
			[][2]string{
				message_inconsistent_db,
			},
		}
		return_reg_error_response(z, w, r, u, err2)
		return nil
	}

	slices.SortFunc(poollist, func(x, y *pool_prop_ui) int {
		return strings.Compare(x.Buckets_directory, y.Buckets_directory)
	})
	var rspn = &pool_list_response{
		response_common: response_common{
			Status:    "success",
			Reason:    nil,
			Timestamp: time.Now().Unix(),
		},
		Pool_list: poollist,
	}
	return_json_repsonse(z, w, r, u, rspn)
	return rspn
}

func make_pool_and_return_response(z *registrar, w http.ResponseWriter, r *http.Request) *pool_prop_response {
	var opr = "make-pool"

	var u = check_user_access_with_error_return(z, w, r, "", false)
	if u == nil {
		return nil
	}

	var args make_pool_arguments
	if !decode_request_body_with_error_return(z, w, r, u, "", opr,
		&args, check_make_pool_arguments) {
		return nil
	}

	// Register pool-name.

	var now int64 = time.Now().Unix()
	var poolname = &pool_mutex_record{
		Owner_uid: u.Uid,
		Timestamp: now,
	}
	var pool = set_with_unique_pool_name(z.table, poolname)

	// Register buckets-directory.

	var path = args.Buckets_directory
	var bd = &bucket_directory_record{
		Pool:      pool,
		Directory: path,
		Timestamp: now,
	}
	var ok, holder = set_ex_buckets_directory(z.table, path, bd)
	if !ok {
		var _ = delete_pool_name_unconditionally(z.table, pool)
		var owner = find_owner_of_pool(z, holder)
		var err1 = &proxy_exc{
			u.Uid,
			http_400_bad_request,
			[][2]string{
				message_buckets_directory_already_taken,
				{"path", path},
				{"owner", owner},
			},
		}
		return_reg_error_response(z, w, r, u, err1)
		return nil
	}

	var conf = &z.conf.Registrar
	assert_fatal(conf.Pool_expiration_days > 0)
	var days = conf.Pool_expiration_days
	var expiration = time.Now().AddDate(0, 0, days).Unix()

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
		Pool:              pool,
		Buckets_directory: path,
		Owner_uid:         u.Uid,
		Owner_gid:         args.Owner_gid,
		Probe_key:         probe,
		Online_status:     true,
		Expiration_time:   expiration,
		Timestamp:         now,
	}
	set_pool(z.table, pool, pooldata)
	set_pool_state(z.table, pool, pool_state_INITIAL, pool_reason_NORMAL)

	var rspn = return_pool_prop(z, w, r, u, pool)
	return rspn
}

func delete_pool_and_return_response(z *registrar, w http.ResponseWriter, r *http.Request, pool string) *success_response {
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
			u.Uid,
			http_400_bad_request,
			[][2]string{
				message_no_pool,
				{"pool", pool},
			},
		}
		return_reg_error_response(z, w, r, u, err1)
		return nil
	}

	// activate_backend(pool)
	// disable_backend_secrets()
	// disable_backend_buckets()

	var rspn = &success_response{
		response_common: response_common{
			Status:    "success",
			Reason:    nil,
			Timestamp: time.Now().Unix(),
		},
	}
	return_json_repsonse(z, w, r, u, rspn)
	return rspn
}

func make_bucket_and_return_response(z *registrar, w http.ResponseWriter, r *http.Request, pool string) *pool_prop_response {
	var opr = "make-bucket"

	var u = check_user_access_with_error_return(z, w, r, pool, false)
	if u == nil {
		return nil
	}

	var args make_bucket_arguments
	if !decode_request_body_with_error_return(z, w, r, u, pool, opr,
		&args, check_make_bucket_arguments) {
		return nil
	}
	var name = args.Bucket
	var policy = intern_ui_bucket_policy(args.Bucket_policy)
	assert_fatal(policy != "")

	var conf = &z.conf.Registrar
	assert_fatal(conf.Bucket_expiration_days > 0)
	var days = conf.Bucket_expiration_days
	var expiration = time.Now().AddDate(0, 0, days).Unix()

	var now int64 = time.Now().Unix()
	var bucket = &bucket_record{
		Pool:            pool,
		Bucket:          name,
		Bucket_policy:   policy,
		Expiration_time: expiration,
		Timestamp:       now,
	}
	var ok1, holder = set_ex_bucket(z.table, name, bucket)
	if !ok1 {
		var owner = find_owner_of_pool(z, holder)
		var err1 = &proxy_exc{
			u.Uid,
			http_400_bad_request,
			[][2]string{
				message_bucket_already_taken,
				{"owner", owner},
			},
		}
		return_reg_error_response(z, w, r, u, err1)
		return nil
	}

	// Make the bucket in the backend.  It ignores all errors.

	if !conf.Postpone_probe_access {
		var _ = probe_access_mux(z.table, pool)
	}

	var rspn = return_pool_prop(z, w, r, u, pool)
	return rspn
}

func delete_bucket_and_return_response(z *registrar, w http.ResponseWriter, r *http.Request, pool string, bucket string) *pool_prop_response {
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

	var ok1 = delete_bucket_unconditionally(z.table, bucket)
	if !ok1 {
		var err1 = &proxy_exc{
			u.Uid,
			http_404_not_found,
			[][2]string{
				message_no_bucket,
				{"bucket", bucket},
			},
		}
		return_reg_error_response(z, w, r, u, err1)
		return nil
	}
	var rspn = return_pool_prop(z, w, r, u, pool)
	return rspn
}

func make_secret_and_return_response(z *registrar, w http.ResponseWriter, r *http.Request, pool string) *pool_prop_response {
	var opr = "make-secret"

	var u = check_user_access_with_error_return(z, w, r, pool, false)
	if u == nil {
		return nil
	}

	var args make_secret_arguments
	if !decode_request_body_with_error_return(z, w, r, u, pool, opr,
		&args, check_make_secret_arguments) {
		return nil
	}
	var policy = intern_ui_secret_policy(args.Secret_policy)
	assert_fatal(policy != "")
	var expiration = args.Expiration_time
	var now = time.Now().Unix()
	var secret = &secret_record{
		Pool:            pool,
		Access_key:      "",
		Secret_key:      generate_secret_key(),
		Secret_policy:   policy,
		Expiration_time: expiration,
		Timestamp:       now,
	}
	var _ = set_with_unique_secret_key(z.table, secret)
	var rspn = return_pool_prop(z, w, r, u, pool)
	return rspn
}

func delete_secret_and_return_response(z *registrar, w http.ResponseWriter, r *http.Request, pool string, secret string) *pool_prop_response {
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
	var ok = delete_secret_key_unconditionally(z.table, secret)
	if !ok {
		slogger.Info("Reg() delete_secret_key() failed (ignored)")
		var err1 = &proxy_exc{
			u.Uid,
			http_400_bad_request,
			[][2]string{
				message_bad_secret,
				{"secret", secret},
			},
		}
		return_reg_error_response(z, w, r, u, err1)
		return nil
	}

	var rpsn *pool_prop_response = return_pool_prop(z, w, r, u, pool)
	return rpsn
}

// RETURN_POOL_PROP returns pool data.
func return_pool_prop(z *registrar, w http.ResponseWriter, r *http.Request, u *user_record, pool string) *pool_prop_response {
	var d = gather_pool_prop(z.table, pool)
	assert_fatal(d != nil)
	var poolprop = copy_pool_prop_to_ui(d)
	var rspn = &pool_prop_response{
		response_common: response_common{
			Status:    "success",
			Reason:    nil,
			Timestamp: time.Now().Unix(),
		},
		Pool_prop: poolprop,
	}
	return_json_repsonse(z, w, r, u, rspn)
	return rspn
}

// CHECK_USER_ACCESS_WITH_ERROR_RETURN checks an access to a pool by a
// user is granted.  It returns a user record. Or, it returns nil when
// access is not granted.  Call it without a pool when deleting a
// pool.
func check_user_access_with_error_return(z *registrar, w http.ResponseWriter, r *http.Request, pool string, firstsession bool) *user_record {
	var conf = &z.conf.Registrar
	_ = conf

	fmt.Println(";; r.RemoteAddr=", r.RemoteAddr)
	fmt.Println(";; X-Real-Ip=", r.Header.Get("X-Real-Ip"))
	fmt.Println(";; X-Remote-User=", r.Header.Get("X-Remote-User"))
	fmt.Println(";; X-Csrf-Token=", r.Header.Get("X-Csrf-Token"))

	var x_remote_user = r.Header.Get("X-Remote-User")
	var dummy = &user_record{
		Uid: x_remote_user,
	}

	// Check if Lens3 is working.

	if !check_lens3_is_running(z.table) {
		slogger.Error("Reg() Lens3 is not running")
		var err1 = &proxy_exc{
			x_remote_user,
			http_500_internal_server_error,
			[][2]string{
				message_lens3_not_running,
			},
		}
		return_reg_error_response(z, w, r, dummy, err1)
		return nil
	}

	// Check the frontend proxy.

	//var client = r.Header.Get("X-Real-Ip")
	var peer = r.RemoteAddr
	if !check_frontend_proxy_trusted(z.trusted_proxies, peer) {
		slogger.Error("Reg() Frontend proxy is untrusted", "ep", peer)
		var err2 = &proxy_exc{
			x_remote_user,
			http_500_internal_server_error,
			[][2]string{
				message_proxy_untrusted,
			},
		}
		return_reg_error_response(z, w, r, dummy, err2)
		return nil
	}

	// Check the user.

	var uid = map_claim_to_uid(z, x_remote_user)
	var u = check_user_account(z, uid, firstsession)
	if u == nil {
		slogger.Warn("Reg() User is not active", "uid", uid)
		var err3 = &proxy_exc{
			u.Uid,
			http_401_unauthorized,
			[][2]string{
				message_bad_user_account,
				{"state", "inactive"},
			},
		}
		return_reg_error_response(z, w, r, dummy, err3)
		return nil
	}

	if !firstsession {
		var ok = check_csrf_tokens(z, w, r, uid)
		if !ok {
			slogger.Warn("Reg() Bad csrf tokens", "uid", uid)
			var err4 = &proxy_exc{
				u.Uid,
				http_401_unauthorized,
				[][2]string{
					message_bad_csrf_tokens,
				},
			}
			return_reg_error_response(z, w, r, u, err4)
			return nil
		}
	}

	if pool == "" {
		return u
	}

	// Check the pool given a pool name.  A FAILURE OF CHECKS MEANS
	// SOMEONE MIGHT HAVE FORGED A REQUEST.

	if !check_pool_naming(pool) {
		slogger.Error("Reg() Bad pool name", "uid", uid, "pool", pool)
		var err5 = &proxy_exc{
			u.Uid,
			http_401_unauthorized,
			[][2]string{
				message_no_pool,
				{"pool", pool},
			},
		}
		return_reg_error_response(z, w, r, u, err5)
		return nil
	}

	var pooldata = get_pool(z.table, pool)
	if pooldata == nil {
		slogger.Error("Reg() No pool", "uid", uid, "pool", pool)
		var err6 = &proxy_exc{
			u.Uid,
			http_401_unauthorized,
			[][2]string{
				message_no_pool,
				{"pool", pool},
			},
		}
		return_reg_error_response(z, w, r, u, err6)
		return nil
	}

	if pooldata.Owner_uid != u.Uid {
		slogger.Error("Reg() Not pool owner",
			"uid", uid, "pool", pool)
		var err7 = &proxy_exc{
			u.Uid,
			http_401_unauthorized,
			[][2]string{
				message_no_pool,
				{"pool", pool},
			},
		}
		return_reg_error_response(z, w, r, u, err7)
		return nil
	}

	var state, reason = check_pool_state(z.table, pool)
	switch state {
	case pool_state_INITIAL, pool_state_READY:
		// OK.
	case pool_state_SUSPENDED:
		// OK.
	case pool_state_DISABLED, pool_state_INOPERABLE:
		slogger.Debug("Reg() Bad pool state", "pool", pool,
			"state", state, "reason", reason)
		var err8 = &proxy_exc{
			u.Uid,
			http_401_unauthorized,
			[][2]string{
				message_bad_pool_state,
				{"pool", pool},
				{"state", string(state)},
				{"reason", string(reason)},
			},
		}
		return_reg_error_response(z, w, r, u, err8)
		return nil
	default:
		panic(nil)
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
// default-allow setting (that is, conf.User_approval=allow).
func check_user_account(z *registrar, uid string, firstsession bool) *user_record {
	var conf = &z.conf.Registrar

	// Reject unregistered users.

	var approving = (conf.User_approval == user_default_allow && firstsession)
	var u1 = get_user(z.table, uid)
	if !approving && u1 == nil {
		return nil
	}

	// Reject users without local accounts.  It is weird as
	// authenticated users without local accounts.

	var uu, err1 = user.Lookup(uid)
	_ = uu
	if err1 != nil {
		// (type of err1 : user.UnknownUserError).
		slogger.Error("Reg() user.Lookup() failed", "uid", uid, "err", err1)
		return nil
	}

	// Check if the user is enabled.

	var now int64 = time.Now().Unix()
	if u1 != nil {
		if !u1.Enabled || u1.Expiration_time < now {
			return nil
		} else {
			extend_user_expiration_time(z, u1)
			return u1
		}
	}

	// Regiter a new user record.

	var u2 = enroll_new_user(z, uid, firstsession)
	return u2
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
		slogger.Error("Reg() Configuration error",
			"user_approval", conf.User_approval,
			"claim_uid_map", conf.Claim_uid_map)
		return nil
	}

	var uu, err1 = user.Lookup(uid)
	if err1 != nil {
		// (err1 : user.UnknownUserError)
		slogger.Error("Reg() user.Lookup(%s) failed", "uid", uid, "err", err1)
		return nil
	}

	var uid_n, err2 = strconv.Atoi(uu.Uid)
	if err2 != nil {
		slogger.Error("Reg() user.Lookup() returns non-numeric uid",
			"uid", uid, "user.User.Uid", uu.Uid)
		return nil
	}
	if len(conf.Uid_allow_range_list) != 0 {
		if !check_int_in_ranges(conf.Uid_allow_range_list, uid_n) {
			slogger.Info("Reg() A new user blocked", "uid", uid)
			return nil
		}
	}
	if check_int_in_ranges(conf.Uid_block_range_list, uid_n) {
		slogger.Info("Reg() A new user blocked", "uid", uid)
		return nil
	}

	var groups = list_groups_of_user(z, uid)

	if len(groups) == 0 {
		slogger.Info("Reg() No groups for a new user", "uid", uid)
		return nil
	}

	slogger.Warn("Reg() Enroll a user automatically", "uid", uid)

	assert_fatal(conf.User_expiration_days > 0)
	var days = conf.User_expiration_days
	var expiration = time.Now().AddDate(0, 0, days).Unix()
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
	if z.verbose && !ok {
		slogger.Debug("Reg() Checking csrf-tokens failed",
			"token", v.Csrf_token, "header", h, "cookie", c)
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
	var timeout = int64(conf.Ui_session_duration)
	set_csrf_token(z.table, uid, data)
	var ok = set_csrf_token_expiry(z.table, uid, timeout)
	if !ok {
		// Ignore an error.
		slogger.Error("Reg() Bad call set_csrf_token_expiry()")
	}
	//var x = get_csrf_token(z.table, uid)
	//fmt.Println("make_csrf_tokens=", x)
	return data
}

// CHECK_MAKE_POOL_ARGUMENTS checks the entires of buckets_directory
// and owner_gid.  It normalizes the path of a buckets-directory (in
// the posix sense).
func check_make_pool_arguments(z *registrar, u *user_record, pool string, data any) reg_error_message {
	var args, ok = data.(*make_pool_arguments)
	assert_fatal(ok)

	// Check bucket-directory path.

	var bd = args.Buckets_directory
	var path = filepath.Clean(bd)
	if !filepath.IsAbs(path) {
		return reg_error_message{
			message_bad_buckets_directory,
			{"path", bd},
		}
	}
	args.Buckets_directory = path

	// Check GID.  UID is not in the arguments.

	var groups []string
	if u.Ephemeral {
		groups = list_groups_of_user(z, u.Uid)
	} else {
		groups = u.Groups
	}
	var gid = args.Owner_gid
	if slices.Index(groups, gid) == -1 {
		return reg_error_message{
			message_bad_group,
			{"group", gid},
		}
	}
	return nil
}

func check_make_bucket_arguments(z *registrar, u *user_record, pool string, data any) reg_error_message {
	var args, ok = data.(*make_bucket_arguments)
	assert_fatal(ok)

	// Check Bucket.
	if !check_bucket_naming(args.Bucket) {
		return reg_error_message{
			message_bad_bucket,
			{"bucket", args.Bucket},
		}
	}
	// Check Bucket_policy.
	if slices.Index(bucket_policy_ui_list, args.Bucket_policy) == -1 {
		return reg_error_message{
			message_bad_policy,
			{"policy", args.Bucket_policy},
		}
	}
	return nil
}

func check_make_secret_arguments(z *registrar, u *user_record, pool string, data any) reg_error_message {
	var args, ok = data.(*make_secret_arguments)
	assert_fatal(ok)

	// Check Secret_policy.
	if slices.Index(secret_policy_ui_list, args.Secret_policy) == -1 {
		return reg_error_message{
			message_bad_policy,
			{"policy", args.Secret_policy},
		}
	}
	// Check Expiration_time.
	var conf = &z.conf.Registrar
	assert_fatal(conf.Secret_expiration_days > 0)
	var days = conf.Secret_expiration_days
	var e = time.Unix(args.Expiration_time, 0)
	var now = time.Now()
	if !(e.After(now.AddDate(0, 0, -1)) && e.Before(now.AddDate(0, 0, days))) {
		return reg_error_message{
			message_bad_expiration,
			{"expiration", e.Format(time.DateOnly)},
		}
	}
	return nil
}

func check_empty_arguments_with_error_return(z *registrar, w http.ResponseWriter, r *http.Request, u *user_record, pool string, opr string) bool {
	var is = r.Body
	var err1 = check_stream_eof(is)
	if err1 == nil {
		return true
	} else {
		slogger.Info("Reg() Garbage in request body")
		var err2 = &proxy_exc{
			u.Uid,
			http_400_bad_request,
			[][2]string{
				message_arguments_not_empty,
			},
		}
		return_reg_error_response(z, w, r, u, err2)
		return false
	}
}

func check_bucket_owner_with_error_return(z *registrar, w http.ResponseWriter, r *http.Request, u *user_record, pool string, bucket string, opr string) bool {
	if !check_bucket_naming_with_error_return(z, w, r, u, bucket) {
		return false
	}
	var b *bucket_record = get_bucket(z.table, bucket)
	if b == nil {
		var err1 = &proxy_exc{
			u.Uid,
			http_404_not_found,
			[][2]string{
				message_no_bucket,
				{"bucket", bucket},
			},
		}
		return_reg_error_response(z, w, r, u, err1)
		return false
	}
	if b.Pool != pool {
		var err2 = &proxy_exc{
			u.Uid,
			http_401_unauthorized,
			[][2]string{
				message_not_bucket_owner,
				{"bucket", bucket},
			},
		}
		return_reg_error_response(z, w, r, u, err2)
		return false
	}
	return true
}

func check_bucket_naming_with_error_return(z *registrar, w http.ResponseWriter, r *http.Request, u *user_record, bucket string) bool {
	var ok = check_bucket_naming(bucket)
	if !ok {
		var err1 = &proxy_exc{
			u.Uid,
			http_400_bad_request,
			[][2]string{
				message_bad_bucket,
				{"bucket", bucket},
			},
		}
		return_reg_error_response(z, w, r, u, err1)
	}
	return ok
}

func check_secret_owner_with_error_return(z *registrar, w http.ResponseWriter, r *http.Request, u *user_record, pool string, secret string, opr string) bool {
	if !check_access_key_naming_with_error_return(z, w, r, u, secret) {
		return false
	}
	var b *secret_record = get_secret(z.table, secret)
	if b == nil {
		var err1 = &proxy_exc{
			u.Uid,
			http_404_not_found,
			[][2]string{
				message_no_secret,
				{"secret", secret},
			},
		}
		return_reg_error_response(z, w, r, u, err1)
		return false
	}
	if b.Pool != pool {
		var err2 = &proxy_exc{
			u.Uid,
			http_401_unauthorized,
			[][2]string{
				message_not_secret_owner,
				{"secret", secret},
			},
		}
		return_reg_error_response(z, w, r, u, err2)
		return false
	}
	return true
}

func check_access_key_naming_with_error_return(z *registrar, w http.ResponseWriter, r *http.Request, u *user_record, secret string) bool {
	var ok = check_access_key_naming(secret)
	if !ok {
		var err1 = &proxy_exc{
			u.Uid,
			http_400_bad_request,
			[][2]string{
				message_bad_secret,
				{"secret", secret},
			},
		}
		return_reg_error_response(z, w, r, u, err1)
	}
	return ok
}

type checker_fn func(z *registrar, u *user_record, pool string, data any) reg_error_message

func decode_request_body_with_error_return(z *registrar, w http.ResponseWriter, r *http.Request, u *user_record, pool string, opr string, data any, check checker_fn) bool {
	var ok1 = decode_request_body(z, r, data)
	if !ok1 {
		var err1 = &proxy_exc{
			u.Uid,
			http_400_bad_request,
			[][2]string{
				message_bad_body_encoding,
				{"op", opr},
			},
		}
		return_reg_error_response(z, w, r, u, err1)
		return false
	}
	var msg = check(z, u, pool, data)
	if msg != nil {
		var err2 = &proxy_exc{
			u.Uid,
			http_400_bad_request,
			msg,
		}
		return_reg_error_response(z, w, r, u, err2)
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
		if z.verbose && err1 == nil {
			slogger.Debug("Reg() Error in reading request body", "err", err1)
		}
		return false
	}
	if !check_fields_filled(data) {
		if z.verbose {
			slogger.Debug("Reg() Unfilled entries in request body")
		}
		return false
	}
	// Check EOF.  Garbage data means an error.
	var is = d.Buffered()
	var err2 = check_stream_eof(is)
	return (err2 == nil)
}

func map_claim_to_uid(z *registrar, x_remote_user string) string {
	//AHOAHOAHO
	return x_remote_user
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
		Pool:              d.pool_record.Pool,
		Buckets_directory: d.Buckets_directory,
		Owner_uid:         d.Owner_uid,
		Owner_gid:         d.Owner_gid,
		Probe_key:         d.Probe_key,
		Online_status:     d.Online_status,
		Expiration_time:   d.pool_record.Expiration_time,
		Timestamp:         d.pool_record.Timestamp,
		// POOL_PROP
		Buckets: copy_bucket_data_to_ui(d.Buckets),
		Secrets: copy_secret_data_to_ui(d.Secrets),
		// USER_RECORD
		User_enabled_status: d.Enabled,
		// POOL_STATE_RECORD
		Backend_state:  d.State,
		Backend_reason: d.Reason,
	}
	return v
}

func copy_bucket_data_to_ui(m []*bucket_record) []*bucket_data_ui {
	var buckets []*bucket_data_ui
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
	var secrets []*secret_data_ui
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

func encode_error_message__(keyvals [][2]string) string {
	fmt.Printf("encode_error_message for=%#v\n", keyvals)

	var b bytes.Buffer
	b.Write([]byte("{"))
	for _, kv := range keyvals {
		var b1, err1 = json.Marshal(kv[0])
		assert_fatal(err1 == nil)
		var _, err2 = b.Write(b1)
		assert_fatal(err2 == nil)
		var _, err3 = b.Write([]byte(":"))
		assert_fatal(err3 == nil)
		var b2, err4 = json.Marshal(kv[1])
		assert_fatal(err4 == nil)
		var _, err5 = b.Write(b2)
		assert_fatal(err5 == nil)
		var _, err6 = b.Write([]byte(","))
		assert_fatal(err6 == nil)
	}
	b.Write([]byte("}"))
	return string(b.Bytes())
}

// FIND_OWNER_OF_POOL finds an owner of a pool for printing
// error messages.  It returns unknown-user, when an owner is not
// found.
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

func intern_ui_secret_policy(policy string) secret_policy {
	switch policy {
	case secret_policy_ui_RW:
		return secret_policy_RW
	case secret_policy_ui_RO:
		return secret_policy_RO
	case secret_policy_ui_WO:
		return secret_policy_WO
	default:
		return ""
	}
}

func intern_ui_bucket_policy(policy string) bucket_policy {
	switch policy {
	case bucket_policy_ui_NONE:
		return bucket_policy_NONE
	case bucket_policy_ui_WO:
		return bucket_policy_WO
	case bucket_policy_ui_RO:
		return bucket_policy_RO
	case bucket_policy_ui_RW:
		return bucket_policy_RW
	default:
		return ""
	}
}

func extend_user_expiration_time(z *registrar, u *user_record) {
	var conf = &z.conf.Registrar
	assert_fatal(conf.User_expiration_days > 0)
	var days = conf.User_expiration_days
	var expiration = time.Now().AddDate(0, 0, days).Unix()
	if u.Expiration_time < expiration {
		u.Expiration_time = expiration
	}
	set_user_raw(z.table, u)
}

func list_groups_of_user(z *registrar, uid string) []string {
	var conf = &z.conf.Registrar

	var uu, err1 = user.Lookup(uid)
	if err1 != nil {
		// (err1 : user.UnknownUserError)
		slogger.Error("Reg() user.Lookup() failed", "uid", uid, "err", err1)
		return nil
	}
	var gids, err2 = uu.GroupIds()
	if err2 != nil {
		slogger.Error("Reg() user.User.GroupIds() failed",
			"uid", uid, "err", err2)
		return nil
	}
	var groups []string
	for _, g1 := range gids {
		var gid_n, err3 = strconv.Atoi(g1)
		if err3 != nil {
			slogger.Error("Reg() user.User.GroupIds() returns non-numeric gid",
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
			slogger.Error("Reg(0 user.LookupGroupId() failed",
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

// DEREGISTER_USER deletes a user, along with its pool.  Deleting a
// pool additionally deletes its assets.
func deregister_user(t *keyval_table, uid string) {
	var poolnames = list_pools_of_user(t, uid)
	for _, pool := range poolnames {
		//var p = gather_pool_prop(t, pool)
		//if p == nil {
		//continue
		//}
		// Ignore errors.
		var _ = deregister_pool(t, pool)
	}
	delete_user(t, uid)
	delete_user_timestamp(t, uid)
}

// DEREGISTER_POOL deletes a pool, along with its buckets-directory,
// buckets, and access-keys.  It returns OK/NG.  It ignores most of
// the errors but only fails when a pool is not found.  IT DOES
// NOTHING TO A BACKEND.  That is, it does not remove or disable
// buckets in the backend.
func deregister_pool(t *keyval_table, pool string) bool {
	//fmt.Println("deregister_pool()", pool)
	var p = gather_pool_prop(t, pool)
	if p == nil {
		slogger.Info("Reg() Deleting a non-existing pool", "pool", pool)
		return false
	}

	// Delete buckets_directory.

	var path = p.Buckets_directory
	var ok1 = delete_buckets_directory_unconditionally(t, path)
	if !ok1 {
		slogger.Info("Reg() Deleting a buckets directory failed (ignored)",
			"pool", pool, "path", path)
	}

	// Delete buckets.

	var bkts = p.Buckets
	for _, b := range bkts {
		assert_fatal(b.Pool == pool)
		var ok2 = delete_bucket_unconditionally(t, b.Bucket)
		if !ok2 {
			slogger.Info("Reg() Deleting a bucket failed (ignored)",
				"pool", pool, "bucket", b.Bucket)
		}
	}

	// Delete access-keys.

	for _, k := range p.Secrets {
		assert_fatal(k.Pool == pool)
		var ok = delete_secret_key_unconditionally(t, k.Access_key)
		if !ok {
			slogger.Info("Reg() Deleting an access-key failed (ignored)",
				"pool", pool, "secret", k.Access_key)
		}
	}

	//erase_backend_ep(self.tables, pool)
	//erase_pool_prop(self.tables, pool)

	delete_pool(t, p.pool_record.Pool)

	return true
}

// NOTE: It cannot obtain a response object.  http.ResponseWriter is
// an instance of http.response, but it is not public.  Note that also
// the field http.Request.Response is null.  Niether a context does
// not have a response.  http.RoundTrip is on the client side.
func return_json_repsonse(z *registrar, w http.ResponseWriter, rqst *http.Request, u *user_record, value any) {
	assert_fatal(u != nil)
	var v1, err1 = json.Marshal(value)
	if err1 != nil {
		slogger.Error("Reg() json.Marshal() failed", "err", err1)
		panic(nil)
	}
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	//io.WriteString(w, string(v1))
	var _, err2 = w.Write(v1)
	if err2 != nil {
		slogger.Error("Reg() Writing reply failed", "err", err2)
	}
	var wf, ok = w.(http.Flusher)
	if ok {
		wf.Flush()
	}
	log_reg_access_by_request(rqst, 200, int64(len(v1)), u.Uid, "_")
	return
}

func return_reg_error_response(z *registrar, w http.ResponseWriter, rqst *http.Request, u *user_record, err *proxy_exc) {
	var code int = err.code
	var reason [][2]string = err.message

	assert_fatal(u != nil)
	var msg = map[string]string{}
	for _, kv := range reason {
		msg[kv[0]] = kv[1]
	}
	var value = &error_response{
		response_common: response_common{
			Status:    "error",
			Reason:    msg,
			Timestamp: time.Now().Unix(),
		},
	}
	var b1, err1 = json.Marshal(value)
	assert_fatal(err1 == nil)
	delay_sleep(z.conf.Registrar.Error_response_delay_ms)
	http.Error(w, string(b1), code)
	//log_access_with_user(rspn, u.Uid)
	log_reg_access_by_request(rqst, code, int64(len(b1)), u.Uid, "-")
}
