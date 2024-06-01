/* Lens3-Reg.  It is a registrar of buckets and secrets. */

// Copyright 2022-2024 RIKEN R-CCS
// SPDX-License-Identifier: BSD-2-Clause

package lens3

// UI expects responses as FastAPI/Starlette's "JSONResponse".
//
// media_type = "application/json"
// json.dumps(
//   content,
//   ensure_ascii=False,
//   allow_nan=False,
//   indent=None,
//   separators=(",", ":"),
// ).encode("utf-8")

// It uses a "double submit cookie" for CSRF prevention used in
// fastapi_csrf_protect.  It uses a cookie+header pair.  A cookie is
// "fastapi-csrf-token" and a header is "X-Csrf-Token".  However, this
// implementes only the header part, assuming the cookie part is
// subsumed by authenitication by httpd.  The CSRF state of a client
// is set by a response of "GET /user_info".  See
// https://github.com/aekasitt/fastapi-csrf-protect.

// ??? NOTE: Maybe, consider adding a "Retry-After" header for 503 error.

import (
	"bytes"
	"fmt"
	//"flag"
	"path/filepath"
	"runtime/debug"
	//"context"
	"encoding/json"
	"io"
	//"log"
	"net"
	//"maps"
	//"math/rand/v2"
	"net/http"
	//"net/http/httputil"
	//"net/url"
	//"os"
	"errors"
	"os/user"
	"slices"
	"strconv"
	"strings"
	"time"
	//"runtime"
)

// UI script is by embeded files.

import "embed"

//go:embed ui
var efs1 embed.FS

//go:embed ui2
var efs2 embed.FS

type registrar struct {
	// EP_PORT is a listening port of Reg (":port").
	ep_port string

	verbose bool

	table *keyval_table

	server *http.Server
	router *http.ServeMux

	determine_expiration_time int64

	trusted_proxies []net.IP

	ch_quit_service chan vacuous

	*reg_conf
	//registrar_conf
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
	Pool          string        `json:"pool"`
	Bucket        string        `json:"name"`
	Bucket_policy bucket_policy `json:"bkt_policy"`
	Timestamp     int64         `json:"modification_time"`
}

type secret_data_ui struct {
	Pool            string `json:"owner"`
	Access_key      string `json:"access_key"`
	Secret_key      string `json:"secret_key"`
	Secret_policy   string `json:"secret_policy"`
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

var the_registrar = registrar{}

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

var map_secret_policy_to_ui = map[secret_policy]string{
	secret_policy_RW: secret_policy_ui_RW,
	secret_policy_RO: secret_policy_ui_RO,
	secret_policy_WO: secret_policy_ui_WO,
}

// REG_ERROR_MESSAGE is an extra error message returned to UI on errors.
type reg_error_message [][2]string

func configure_registrar(z *registrar, t *keyval_table, q chan vacuous, c *reg_conf) {
	z.table = t
	z.ch_quit_service = q
	z.reg_conf = c
	z.verbose = true

	var conf = &z.Registrar
	z.ep_port = net.JoinHostPort("", strconv.Itoa(conf.Port))

	var addrs []net.IP = convert_hosts_to_addrs(conf.Trusted_proxy_list)
	logger.debugf("Reg(%s) trusted_proxies=(%v)", z.ep_port, addrs)
	if len(addrs) == 0 {
		panic("No trusted proxies")
	}
	z.trusted_proxies = addrs
}

func start_registrar(z *registrar) {
	//fmt.Println("start_registrar() z=", z)
	//var conf = &z.Registrar
	z.router = http.NewServeMux()
	z.server = &http.Server{
		Addr:    z.ep_port,
		Handler: z.router,
	}

	// Root "/" requests are redirected.

	z.router.HandleFunc("GET /{$}", func(w http.ResponseWriter, r *http.Request) {
		defer handle_registrar_exc(z, w, r)
		fmt.Println("Reg.GET /")
		logger.debug("Reg.GET /")
		//	defer func() {
		//		var x = recover()
		//		switch e := x.(type) {
		//		case nil:
		//		case *proxy_exc:
		//			fmt.Println("RECOVER!", e)
		//			http.Error(w, e.m, e.code)
		//		default:
		//			http.Error(w, "BAD", http_500_internal_server_error)
		//		}
		//	}()
		http.Redirect(w, r, "./ui/index.html", http.StatusSeeOther)
	})

	z.router.HandleFunc("GET /ui/index.html", func(w http.ResponseWriter, r *http.Request) {
		defer handle_registrar_exc(z, w, r)
		var _ = return_ui_script(z, w, r, "ui/index.html")
	})

	z.router.HandleFunc("GET /ui2/index.html", func(w http.ResponseWriter, r *http.Request) {
		defer handle_registrar_exc(z, w, r)
		var _ = return_ui_script(z, w, r, "ui2/index.html")
	})

	z.router.HandleFunc("GET /ui/", func(w http.ResponseWriter, r *http.Request) {
		defer handle_registrar_exc(z, w, r)
		var _ = return_file(z, w, r, r.URL.Path, &efs1)
	})

	z.router.HandleFunc("GET /ui2/", func(w http.ResponseWriter, r *http.Request) {
		defer handle_registrar_exc(z, w, r)
		var _ = return_file(z, w, r, r.URL.Path, &efs2)
	})

	z.router.HandleFunc("GET /user-info", func(w http.ResponseWriter, r *http.Request) {
		logger.debug("Reg.GET /user-info")
		defer handle_registrar_exc(z, w, r)
		var _ = return_user_info(z, w, r)
	})

	z.router.HandleFunc("GET /pool", func(w http.ResponseWriter, r *http.Request) {
		defer handle_registrar_exc(z, w, r)
		var _ = list_pool_and_return_response(z, w, r, "")
	})

	z.router.HandleFunc("GET /pool/{pool}", func(w http.ResponseWriter, r *http.Request) {
		defer handle_registrar_exc(z, w, r)
		var pool = r.PathValue("pool")
		var _ = list_pool_and_return_response(z, w, r, pool)
	})

	// A POST request makes a pool.

	z.router.HandleFunc("POST /pool", func(w http.ResponseWriter, r *http.Request) {
		defer handle_registrar_exc(z, w, r)
		var _ = make_pool_and_return_response(z, w, r)
	})

	z.router.HandleFunc("DELETE /pool/{pool}", func(w http.ResponseWriter, r *http.Request) {
		defer handle_registrar_exc(z, w, r)
		var pool = r.PathValue("pool")
		var _ = delete_pool_and_return_response(z, w, r, pool)
	})

	// A PUT request makes a bucket.

	z.router.HandleFunc("PUT /pool/{pool}/bucket", func(w http.ResponseWriter, r *http.Request) {
		defer handle_registrar_exc(z, w, r)
		var pool = r.PathValue("pool")
		var _ = make_bucket_and_return_response(z, w, r, pool)
	})

	z.router.HandleFunc("DELETE /pool/{pool}/bucket/{bucket}", func(w http.ResponseWriter, r *http.Request) {
		defer handle_registrar_exc(z, w, r)
		var pool = r.PathValue("pool")
		var bucket = r.PathValue("bucket")
		var _ = delete_bucket_and_return_response(z, w, r, pool, bucket)
	})

	// A POST request makes a secret.

	z.router.HandleFunc("POST /pool/{pool}/secret", func(w http.ResponseWriter, r *http.Request) {
		defer handle_registrar_exc(z, w, r)
		var pool = r.PathValue("pool")
		var _ = make_secret_and_return_response(z, w, r, pool)
	})

	z.router.HandleFunc("DELETE /pool/{pool}/secret/{secret}", func(w http.ResponseWriter, r *http.Request) {
		defer handle_registrar_exc(z, w, r)
		var pool = r.PathValue("pool")
		var secret = r.PathValue("secret")
		var _ = delete_secret_and_return_response(z, w, r, pool, secret)
	})

	logger.infof("Reg(%s) Start Reg", z.ep_port)
	for {
		var err1 = z.server.ListenAndServe()
		logger.infof("Reg(%s) ListenAndServe() done err=%v", z.ep_port, err1)
	}
}

func handle_registrar_exc(z *registrar, w http.ResponseWriter, r *http.Request) {
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

func return_ui_script(z *registrar, w http.ResponseWriter, r *http.Request, path string) *string {
	var data1, err1 = efs1.ReadFile(path)
	if err1 != nil {
		http.Error(w, "BAD", http_500_internal_server_error)
		return nil
	}
	var parameters = (`<script type="text/javascript">const base_path_="` +
		z.Registrar.Base_path + `";</script>`)
	var data2 = strings.Replace(string(data1),
		"PLACE_BASE_PATH_SETTING_HERE", parameters, 1)
	//fmt.Println(string(data2))
	io.WriteString(w, data2)
	return &data2
}

func return_file(z *registrar, w http.ResponseWriter, r *http.Request, path string, efs1 *embed.FS) *[]byte {
	var data1, err1 = efs1.ReadFile(path)
	if err1 != nil {
		http.Error(w, "BAD", http_500_internal_server_error)
		return nil
	}
	io.WriteString(w, string(data1))
	return &data1
}

// RETURN_USER_INFO returns a response for GET "/user-info".  This
// request is assumed as the first request, and it initializes the
// CSRF state.  It makes a list of groups when a user was added
// automatically, because groups may change from time to time.  The
// groups may be empty.
func return_user_info(z *registrar, w http.ResponseWriter, r *http.Request) *user_info_response {
	var opr = "user-info"
	var u = grant_access_with_error_return(z, w, r, "", true)
	if u == nil {
		return nil
	}
	if !check_empty_arguments_with_error_return(z, w, r, "", opr) {
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
	var now = time.Now().Unix()
	var rspn = &user_info_response{
		response_common: response_common{
			Status:    "success",
			Reason:    nil,
			Timestamp: now,
		},
		Csrf_token: csrf.Csrf_token_h,
		User_info:  *info,
	}
	return_json_repsonse(z, w, r, rspn)
	return rspn
}

// LIST_POOL_AND_RETURN_RESPONSE returns a record of a pool with a
// given pool-name, or a list of pools owned by a user for "".
func list_pool_and_return_response(z *registrar, w http.ResponseWriter, r *http.Request, pool string) *pool_list_response {
	var opr = "list-pool"
	var u = grant_access_with_error_return(z, w, r, pool, false)
	if u == nil {
		return nil
	}
	if !check_empty_arguments_with_error_return(z, w, r, pool, opr) {
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
		return_reg_error_response(z, w, r, http_400_bad_request,
			[][2]string{
				message_No_pool,
				{"pool", pool},
			})
		return nil
	}
	if pool != "" && len(poollist) > 1 {
		logger.errf("Reg() multiple pools with the same id (pool=%s)",
			pool)
		return_reg_error_response(z, w, r, http_500_internal_server_error,
			[][2]string{message_internal_error})
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
	return_json_repsonse(z, w, r, rspn)
	return rspn
}

func make_pool_and_return_response(z *registrar, w http.ResponseWriter, r *http.Request) *pool_prop_response {
	var opr = "make-pool"

	var u = grant_access_with_error_return(z, w, r, "", false)
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
		return_reg_error_response(z, w, r, http_400_bad_request,
			[][2]string{
				message_Buckets_directory_already_taken,
				{"path", path},
				{"owner", owner},
			})
		return nil
	}

	var conf = &z.Registrar
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

	var rspn = return_pool_prop(z, w, r, pool)
	return rspn
}

func delete_pool_and_return_response(z *registrar, w http.ResponseWriter, r *http.Request, pool string) *success_response {
	var opr = "delete-pool"
	var u = grant_access_with_error_return(z, w, r, pool, false)
	if u == nil {
		return nil
	}
	if !check_empty_arguments_with_error_return(z, w, r, pool, opr) {
		return nil
	}

	var d = gather_pool_prop(z.table, pool)
	if d == nil {
		return_reg_error_response(z, w, r, http_400_bad_request,
			[][2]string{
				message_No_pool,
				{"pool", pool},
			})
		return nil
	}

	// activate_backend(pool)
	// disable_backend_secrets()
	// disable_backend_buckets()

	// Delete buckets_directory.

	var path = d.Buckets_directory
	var ok1 = delete_buckets_directory_unconditionally(z.table, path)
	if !ok1 {
		logger.infof("delete_buckets_directory failed (ignored)")
	}

	// Delete buckets.

	var bkts = d.Buckets
	for _, b := range bkts {
		assert_fatal(b.Pool == pool)
		var ok2 = delete_bucket_unconditionally(z.table, b.Bucket)
		if !ok2 {
			logger.infof("delete_bucket failed (ignored)")
		}
	}

	// Delete access-keys.

	for _, k := range d.Secrets {
		assert_fatal(k.Pool == pool)
		var ok = delete_secret_key_unconditionally(z.table, k.Access_key)
		if !ok {
			logger.infof("delete_secret_key failed (ignored)")
		}
	}

	// DOIT OR NOT DOIT: set none-policy to buckets for MinIO backend.

	//erase_backend_ep(self.tables, pool)
	//erase_pool_prop(self.tables, pool)

	delete_pool(z.table, pool)

	var rspn = &success_response{
		response_common: response_common{
			Status:    "success",
			Reason:    nil,
			Timestamp: time.Now().Unix(),
		},
	}
	return_json_repsonse(z, w, r, rspn)
	return rspn
}

func make_bucket_and_return_response(z *registrar, w http.ResponseWriter, r *http.Request, pool string) *pool_prop_response {
	var opr = "make-bucket"

	var u = grant_access_with_error_return(z, w, r, pool, false)
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

	var conf = &z.Registrar
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
		return_reg_error_response(z, w, r, http_400_bad_request,
			[][2]string{
				message_Bucket_already_taken,
				{"owner", owner},
			})
		return nil
	}

	// Make the bucket in the backend.  It ignores all errors.

	if !conf.Postpone_probe_access {
		var _ = probe_access_mux(z.table, pool)
	}

	var rspn = return_pool_prop(z, w, r, pool)
	return rspn
}

func delete_bucket_and_return_response(z *registrar, w http.ResponseWriter, r *http.Request, pool string, bucket string) *pool_prop_response {
	var opr = "delete-bucket"
	var u = grant_access_with_error_return(z, w, r, pool, false)
	if u == nil {
		return nil
	}
	if !check_bucket_owner_with_error_return(z, w, r, pool, bucket, opr) {
		return nil
	}
	if !check_empty_arguments_with_error_return(z, w, r, pool, opr) {
		return nil
	}

	var ok1 = delete_bucket_unconditionally(z.table, bucket)
	if !ok1 {
		return_reg_error_response(z, w, r, http_404_not_found,
			[][2]string{
				message_No_bucket,
				{"bucket", bucket},
			})
		return nil
	}
	var rspn = return_pool_prop(z, w, r, pool)
	return rspn
}

func make_secret_and_return_response(z *registrar, w http.ResponseWriter, r *http.Request, pool string) *pool_prop_response {
	var opr = "make-secret"
	var u = grant_access_with_error_return(z, w, r, pool, false)
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
	var rspn = return_pool_prop(z, w, r, pool)
	return rspn
}

func delete_secret_and_return_response(z *registrar, w http.ResponseWriter, r *http.Request, pool string, secret string) *pool_prop_response {
	var opr = "delete-secret"
	var u = grant_access_with_error_return(z, w, r, pool, false)
	if u == nil {
		return nil
	}
	if !check_secret_owner_with_error_return(z, w, r, pool, secret, opr) {
		return nil
	}
	if !check_empty_arguments_with_error_return(z, w, r, pool, opr) {
		return nil
	}

	//ensure_secret_owner_only(self.tables, access_key, pool_id)
	var ok = delete_secret_key_unconditionally(z.table, secret)
	if !ok {
		logger.infof("delete_secret_key failed (ignored)")
		return_reg_error_response(z, w, r, http_400_bad_request,
			[][2]string{
				message_Bad_secret,
				{"secret", secret},
			})
		return nil
	}

	var rpsn *pool_prop_response = return_pool_prop(z, w, r, pool)
	return rpsn
}

// RETURN_POOL_PROP returns pool data.
func return_pool_prop(z *registrar, w http.ResponseWriter, r *http.Request, pool string) *pool_prop_response {
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
	return_json_repsonse(z, w, r, rspn)
	return rspn
}

func return_json_repsonse(z *registrar, w http.ResponseWriter, r *http.Request, rspn any) {
	var v1, err1 = json.Marshal(rspn)
	if err1 != nil {
		panic(err1)
	}
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	io.WriteString(w, string(v1))
	log_access(r, http_200_OK)
	return
}

func return_reg_error_response(z *registrar, w http.ResponseWriter, r *http.Request, code int, reason [][2]string) {
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
	log_access(r, code)
}

// GRANT_ACCESS_WITH_ERROR_RETURN checks an access to a pool by a user
// is granted.  It returns a user record on success.  It does not
// check the pool-state on deleting a pool.
func grant_access_with_error_return(z *registrar, w http.ResponseWriter, r *http.Request, pool string, firstsession bool) *user_record {
	var conf = &z.Registrar
	_ = conf

	fmt.Println(";; r.RemoteAddr=", r.RemoteAddr)
	fmt.Println(";; X-Real-Ip=", r.Header.Get("X-Real-Ip"))
	fmt.Println(";; X-Remote-User=", r.Header.Get("X-Remote-User"))
	fmt.Println(";; X-Csrf-Token=", r.Header.Get("X-Csrf-Token"))

	if check_lens3_is_running(z.table) {
		logger.errf("Reg() lens3 is not running")
		return_reg_error_response(z, w, r, http_500_internal_server_error,
			[][2]string{
				message_Lens3_not_running,
			})
		return nil
	}

	// Check on the frontend proxy.

	//var client = r.Header.Get("X-Real-Ip")
	var peer = r.RemoteAddr
	if !check_frontend_proxy_trusted(z.trusted_proxies, peer) {
		logger.errf("Reg() frontend proxy is untrusted: ep=(%v)", peer)
		return_reg_error_response(z, w, r, http_500_internal_server_error,
			[][2]string{
				message_Bad_proxy_configuration,
			})
		return nil
	}

	// Check on the user.

	var x_remote_user = r.Header.Get("X-Remote-User")
	var uid = map_claim_to_uid(z, x_remote_user)
	var u = check_user_account(z, uid, firstsession)
	if u == nil {
		logger.warnf("Reg() user is not active: uid=(%s)", uid)
		return_reg_error_response(z, w, r, http_401_unauthorized,
			[][2]string{
				message_Bad_user_account,
				{"state", "inactive"},
			})
		return nil
	}

	if !firstsession {
		var ok = check_csrf_tokens(z, w, r, uid)
		if !ok {
			logger.warnf("Reg() Bad csrf tokens: uid=(%s)", uid)
			return_reg_error_response(z, w, r, http_401_unauthorized,
				[][2]string{
					message_Bad_csrf_tokens,
				})
			return nil
		}
	}

	if pool == "" {
		return u
	}

	// Check on the pool given a pool-name.

	if !check_pool_naming(pool) {
		logger.debugf("Reg() Bad pool: uid=(%s) pool=(%s)", uid, pool)
		return_reg_error_response(z, w, r, http_401_unauthorized,
			[][2]string{
				message_Bad_pool,
				{"pool", pool},
			})
		return nil
	}

	var pooldata = get_pool(z.table, pool)
	if pooldata == nil {
		logger.debugf("Reg() No pool: uid=(%s) pool=(%s)", uid, pool)
		return_reg_error_response(z, w, r, http_401_unauthorized,
			[][2]string{
				message_No_pool,
				{"pool", pool},
			})
		return nil
	}
	if pooldata.Owner_uid != u.Uid {
		logger.debugf("Reg() Not pool owner: uid=(%s) pool=(%s)", uid, pool)
		return_reg_error_response(z, w, r, http_401_unauthorized,
			[][2]string{
				message_Not_pool_owner,
				{"pool", pool},
			})
		return nil
	}

	var DO_CHECK_POOL_STATE = false //AHOAHOAHO
	if pool != "" && DO_CHECK_POOL_STATE {
		if !check_pool_state(z.table, pool) {
			//return nil
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
// default-allow setting (that is, conf.User_approval=allow).
func check_user_account(z *registrar, uid string, firstsession bool) *user_record {
	var conf = &z.Registrar

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
		logger.errf("Reg() user.Lookup(%s) fails: err=(%v)", uid, err1)
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

	var u2 = register_new_user(z, uid, firstsession)
	return u2
}

// REGISTER_NEW_USER registers a user at an access to the registrar.
// It checks the unix account.  The new record has empty groups.
func register_new_user(z *registrar, uid string, firstsession bool) *user_record {
	var conf = &z.Registrar
	var approving = (conf.User_approval == user_default_allow && firstsession)
	assert_fatal(approving)

	if conf.Claim_uid_map == claim_uid_map_map {
		logger.errf("Reg() configuration error:"+
			" user_approval=%s claim_uid_map=%s",
			conf.User_approval, conf.Claim_uid_map)
		return nil
	}

	var uu, err1 = user.Lookup(uid)
	if err1 != nil {
		// (err1 : user.UnknownUserError)
		logger.errf("Reg() user.Lookup(%s) fails: err=(%v)", uid, err1)
		return nil
	}

	var uid_n, err2 = strconv.Atoi(uu.Uid)
	if err2 != nil {
		logger.errf("Reg() user.Lookup(%s) returns non-numeric uid=(%s)",
			uid, uu.Uid)
		return nil
	}
	if len(conf.Uid_allow_range_list) != 0 {
		if !check_int_in_ranges(conf.Uid_allow_range_list, uid_n) {
			logger.infof("Reg() a new user blocked: uid=(%s)", uid)
			return nil
		}
	}
	if check_int_in_ranges(conf.Uid_block_range_list, uid_n) {
		logger.infof("Reg() a new user blocked: uid=(%s)", uid)
		return nil
	}

	var groups = list_groups_of_user(z, uid)

	if len(groups) == 0 {
		logger.infof("no groups for a new user: uid=(%s)", uid)
		return nil
	}

	logger.infof("Reg() registering a new user: uid=(%s)", uid)

	// It doesn't care races...

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
	set_user_force(z.table, newuser)
	return newuser
}

func check_csrf_tokens(z *registrar, w http.ResponseWriter, r *http.Request, uid string) bool {
	var v *csrf_token_record = get_csrf_token(z.table, uid)
	var h = r.Header.Get("X-Csrf-Token")
	if !(v != nil && h != "" && v.Csrf_token_h == h) {
		fmt.Println("csrf h=", h, "v=", v)
	}
	return (v != nil && h != "" && v.Csrf_token_h == h)
}

func make_csrf_tokens(z *registrar, uid string) *csrf_token_record {
	var conf = &z.Registrar
	var now = time.Now().Unix()
	var data = &csrf_token_record{
		Csrf_token_c: generate_random_key(),
		Csrf_token_h: generate_random_key(),
		Timestamp:    now,
	}
	var timeout = int64(conf.Ui_session_duration)
	set_csrf_token(z.table, uid, data)
	var ok = set_csrf_token_expiry(z.table, uid, timeout)
	if !ok {
		// Ignore an error.
		logger.errf("Mux() Bad call set_csrf_token_expiry()")
	}
	//var x = get_csrf_token(z.table, uid)
	//fmt.Println("make_csrf_tokens=", x)

	return data
}

func check_pool_state(t *keyval_table, pool string) bool {
	var reject_initial_state = false
	//AHOAHOAHO var state, _ = update_pool_state(t, pool, permitted)
	var state = pool_state_INITIAL //AHOAHOAHO
	switch state {
	case pool_state_INITIAL:
		if reject_initial_state {
			logger.errf("Mux(pool=%s) is in initial state.", pool)
			//raise(reg_error(403, "Pool is in initial state"))
			return false
		}
	case pool_state_READY:
		// Skip.
	case pool_state_SUSPENDED:
		//raise(reg_error(503, "Pool suspended"))
		return false
	case pool_state_DISABLED:
		//raise(reg_error(403, "Pool disabled"))
		return false
	case pool_state_INOPERABLE:
		//raise(reg_error(403, "Pool inoperable"))
		return false
	default:
		assert_fatal(false)
	}
	return true
}

func check_pool_owner__(t *keyval_table, uid string, pool string) bool {
	var pooldata = get_pool(t, pool)
	if pooldata != nil && pooldata.Owner_uid == uid {
		return true
	} else {
		return false
	}
}

// CHECK_MAKE_POOL_ARGUMENTS checks the entires of buckets_directory
// and owner_gid.  It normalizes the path of a buckets-directory (in
// the posix sense).
func check_make_pool_arguments(z *registrar, u *user_record, pool string, data any) reg_error_message {
	var args, ok = data.(*make_pool_arguments)
	if !ok {
		panic("(internal)")
	}

	// Check bucket-directory path.

	var bd = args.Buckets_directory
	var path = filepath.Clean(bd)
	if !filepath.IsAbs(path) {
		return reg_error_message{
			message_Bad_buckets_directory,
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
			message_Bad_group,
			{"group", gid},
		}
	}
	return nil
}

func check_make_bucket_arguments(z *registrar, u *user_record, pool string, data any) reg_error_message {
	var args, ok = data.(*make_bucket_arguments)
	if !ok {
		panic("(internal)")
	}
	// Check Bucket.
	if !check_bucket_naming(args.Bucket) {
		return reg_error_message{
			message_Bad_bucket,
			{"bucket", args.Bucket},
		}
	}
	// Check Bucket_policy.
	if slices.Index(bucket_policy_ui_list, args.Bucket_policy) == -1 {
		return reg_error_message{
			message_Bad_policy,
			{"policy", args.Bucket_policy},
		}
	}
	return nil
}

func check_make_secret_arguments(z *registrar, u *user_record, pool string, data any) reg_error_message {
	var args, ok = data.(*make_secret_arguments)
	if !ok {
		panic("(internal)")
	}
	// Check Secret_policy.
	if slices.Index(secret_policy_ui_list, args.Secret_policy) == -1 {
		return reg_error_message{
			message_Bad_policy,
			{"policy", args.Secret_policy},
		}
	}
	// Check Expiration_time.
	var conf = &z.Registrar
	assert_fatal(conf.Secret_expiration_days > 0)
	var days = conf.Secret_expiration_days
	var e = time.Unix(args.Expiration_time, 0)
	var now = time.Now()
	if !(e.After(now.AddDate(0, 0, -1)) && e.Before(now.AddDate(0, 0, days))) {
		return reg_error_message{
			message_Bad_expiration,
			{"expiration", e.Format(time.DateOnly)},
		}
	}
	return nil
}

func check_bucket_naming_with_error_return(z *registrar, w http.ResponseWriter, r *http.Request, bucket string) bool {
	var ok = check_bucket_naming(bucket)
	if !ok {
		return_reg_error_response(z, w, r, http_400_bad_request,
			[][2]string{
				message_Bad_bucket,
				{"bucket", bucket},
			})
	}
	return ok
}

func check_access_key_naming_with_error_return(z *registrar, w http.ResponseWriter, r *http.Request, secret string) bool {
	var ok = check_access_key_naming(secret)
	if !ok {
		return_reg_error_response(z, w, r, http_400_bad_request,
			[][2]string{
				message_Bad_secret,
				{"secret", secret},
			})
	}
	return ok
}

func check_empty_arguments_with_error_return(z *registrar, w http.ResponseWriter, r *http.Request, pool string, opr string) bool {
	var is = r.Body
	var err1 = check_stream_eof(is)
	if err1 == nil {
		return true
	} else {
		if z.verbose && err1 == nil {
			logger.warnf("garbage in request body")
		}
		return_reg_error_response(z, w, r, http_400_bad_request,
			[][2]string{
				message_Arguments_not_empty,
			})
		return false
	}
}

func check_bucket_owner_with_error_return(z *registrar, w http.ResponseWriter, r *http.Request, pool string, bucket string, opr string) bool {
	if !check_bucket_naming_with_error_return(z, w, r, bucket) {
		return false
	}
	var b *bucket_record = get_bucket(z.table, bucket)
	if b == nil {
		return_reg_error_response(z, w, r, http_404_not_found,
			[][2]string{
				message_No_bucket,
				{"bucket", bucket},
			})
		return false
	}
	if b.Pool != pool {
		return_reg_error_response(z, w, r, http_401_unauthorized,
			[][2]string{
				message_Not_bucket_owner,
				{"bucket", bucket},
			})
		return false
	}
	return true
}

func check_secret_owner_with_error_return(z *registrar, w http.ResponseWriter, r *http.Request, pool string, secret string, opr string) bool {
	if !check_access_key_naming_with_error_return(z, w, r, secret) {
		return false
	}
	var b *secret_record = get_secret(z.table, secret)
	if b == nil {
		return_reg_error_response(z, w, r, http_404_not_found,
			[][2]string{
				message_No_secret,
				{"secret", secret},
			})
		return false
	}
	if b.Pool != pool {
		return_reg_error_response(z, w, r, http_401_unauthorized,
			[][2]string{
				message_Not_secret_owner,
				{"secret", secret},
			})
		return false
	}
	return true
}

type checker_fn func(z *registrar, u *user_record, pool string, data any) reg_error_message

func decode_request_body_with_error_return(z *registrar, w http.ResponseWriter, r *http.Request, u *user_record, pool string, opr string, data any, check checker_fn) bool {
	var ok1 = decode_request_body(z, r, data)
	if !ok1 {
		return_reg_error_response(z, w, r, http_400_bad_request,
			[][2]string{
				message_Bad_body_encoding,
				{"op", opr},
			})
		return false
	}
	var msg = check(z, u, pool, data)
	if msg != nil {
		return_reg_error_response(z, w, r, http_400_bad_request,
			msg)
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
			logger.debugf("error in reading request body: err=(%v)", err1)
		}
		return false
	}
	if !check_fields_filled(data) {
		if z.verbose {
			logger.debugf("unfilled entries in request body")
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
		S3_url:        z.UI.S3_url,
		Footer_banner: z.UI.Footer_banner,
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
			Bucket_policy: d.Bucket_policy,
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
			Secret_policy:   map_secret_policy_to_ui[d.Secret_policy],
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
	var conf = &z.Registrar
	assert_fatal(conf.User_expiration_days > 0)
	var days = conf.User_expiration_days
	var expiration = time.Now().AddDate(0, 0, days).Unix()
	if u.Expiration_time < expiration {
		u.Expiration_time = expiration
	}
	set_user_force(z.table, u)
}

func list_groups_of_user(z *registrar, uid string) []string {
	var conf = &z.Registrar

	var uu, err1 = user.Lookup(uid)
	if err1 != nil {
		// (err1 : user.UnknownUserError)
		logger.errf("Reg() user.Lookup(%s) fails: err=(%v)", uid, err1)
		return nil
	}
	var gids, err2 = uu.GroupIds()
	if err2 != nil {
		logger.errf("Reg() user.GroupIds(%s) failed: err=(%v)", uid, err2)
		return nil
	}
	var groups []string
	for _, g1 := range gids {
		var gid_n, err3 = strconv.Atoi(g1)
		if err3 != nil {
			logger.errf("Reg() user.GroupIds(%s) returns non-numeric gid=(%s)",
				uid, g1)
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
			logger.errf("user.LookupGroupId(%s) failed: err=(%v)", g1, err4)
			continue
		}
		groups = append(groups, gr.Name)
	}
	return groups
}
