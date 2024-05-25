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
	"log"
	"net"
	//"maps"
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
	ep string

	table *keyval_table

	server *http.Server
	router *http.ServeMux

	determine_expiration_time int64

	trusted_proxies []net.IP

	verbose bool

	*reg_conf
	//registrar_conf
}

type response_to_ui interface{ response_union() }

func (*pool_data_response) response_union() {}
func (*user_info_response) response_union() {}

// ???_RESPONSE is a json format of a response to UI.  See the
// function set_pool_data() in "v1/ui/src/lens3c.ts".  Status is
// "success" or "error".
type response_common struct {
	Status    string            `json:"status"`
	Reason    map[string]string `json:"reason"`
	Timestamp int64             `json:"time"`
	//X_csrf_token string            `json:"x_csrf_token"`
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

type pool_data_response struct {
	response_common
	Pool_data *pool_data_ui `json:"pool_desc"`
}

type pool_list_response struct {
	response_common
	Pool_list []*pool_data_ui `json:"pool_list"`
}

type pool_data_ui struct {
	Pool                string            `json:"pool_name"`
	Buckets_directory   string            `json:"buckets_directory"`
	Owner_uid           string            `json:"owner_uid"`
	Owner_gid           string            `json:"owner_gid"`
	Buckets             []*bucket_desc_ui `json:"buckets"`
	Secrets             []*secret_desc_ui `json:"secrets"`
	Probe_key           string            `json:"probe_key"`
	Expiration_time     int64             `json:"expiration_time"`
	Online_status       bool              `json:"online_status"`
	User_enabled_status bool              `json:"user_enabled_status"`
	Backend_state       pool_state        `json:"minio_state"`
	Backend_reason      pool_reason       `json:"minio_reason"`
	Timestamp           int64             `json:"modification_time"`
}

type bucket_desc_ui struct {
	Pool          string        `json:"pool"`
	Bucket        string        `json:"name"`
	Bucket_policy bucket_policy `json:"bkt_policy"`
	Timestamp     int64         `json:"modification_time"`
}

type secret_desc_ui struct {
	Pool            string `json:"owner"`
	Access_key      string `json:"access_key"`
	Secret_key      string `json:"secret_key"`
	Secret_policy   string `json:"secret_policy"`
	Expiration_time int64  `json:"expiration_time"`
	Timestamp       int64  `json:"modification_time"`
}

type user_info_ui struct {
	Reg_version   string   `json:"api_version"`
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
	bucket_policy_ui_NONE     string = "none"
	bucket_policy_ui_UPLOAD   string = "upload"
	bucket_policy_ui_DOWNLOAD string = "download"
	bucket_policy_ui_PUBLIC   string = "public"
)

var bucket_policy_ui_list = []string{
	bucket_policy_ui_NONE,
	bucket_policy_ui_UPLOAD,
	bucket_policy_ui_DOWNLOAD,
	bucket_policy_ui_PUBLIC,
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

// REG_MESSAGE is an extra error message returned to UI on errors.
type reg_message [][2]string

var (
	message_internal_error = [][2]string{{"message", "(internal)"}}
)

var (
	message_Lens3_not_running = [2]string{
		"message", "Lens3 is not running"}
	message_Bad_proxy_configuration = [2]string{
		"message", "Bad proxy configuration"}
	message_Bad_user_account = [2]string{
		"message", "Missing or bad user_account"}
	message_Bad_csrf_tokens = [2]string{
		"message", "Missing or bad csrf-tokens"}
	message_No_pool = [2]string{
		"message", "No pool"}
	message_No_bucket = [2]string{
		"message", "No bucket"}
	message_No_secret = [2]string{
		"message", "No secret"}
	message_Not_pool_owner = [2]string{
		"message", "Not pool owner"}
	message_Not_bucket_owner = [2]string{
		"message", "Not bucket owner"}
	message_Not_secret_owner = [2]string{
		"message", "Not secret owner"}
	message_Arguments_not_empty = [2]string{
		"message", "Arguments not empty"}
	message_Bad_body_encoding = [2]string{
		"message", "Bad body encoding"}
	message_Bad_group = [2]string{
		"message", "Bad group"}
	message_Bad_pool = [2]string{
		"message", "Bad pool"}
	message_Bad_buckets_directory = [2]string{
		"message", "Buckets-directory is not absolute"}
	message_Bad_bucket = [2]string{
		"message", "Bad bucket"}
	message_Bad_secret = [2]string{
		"message", "Bad secret"}
	message_Bad_policy = [2]string{
		"message", "Bad policy"}
	message_Bad_expiration = [2]string{
		"message", "Bad expiration"}
	message_Bucket_already_taken = [2]string{
		"message", "Bucket already taken"}
	message_Buckets_directory_already_taken = [2]string{
		"message", "Buckets directory already taken"}
)

func configure_registrar(z *registrar, t *keyval_table, c *reg_conf) {
	z.table = t
	z.reg_conf = c
	z.verbose = true

	var conf = &z.Registrar
	z.ep = net.JoinHostPort("", strconv.Itoa(conf.Port))

	var addrs []net.IP
	for _, h := range conf.Trusted_proxy_list {
		var ips, err1 = net.LookupIP(h)
		if err1 != nil {
			logger.warnf("net.LookupIP(%s) fails: err=(%v)", h, err1)
			continue
		}
		addrs = append(addrs, ips...)
	}
	logger.debugf("Reg(%s) trusted_proxies=(%v)", z.ep, addrs)
	if len(addrs) == 0 {
		panic("No trusted proxies")
	}
	z.trusted_proxies = addrs
}

func start_registrar(z *registrar) {
	fmt.Println("start_registrar() z=", z)
	//var conf = &z.Registrar
	z.router = http.NewServeMux()
	z.server = &http.Server{
		Addr:    z.ep,
		Handler: z.router,
	}

	// Root "/" requests are redirected.

	z.router.HandleFunc("GET /{$}", func(w http.ResponseWriter, r *http.Request) {
		defer handle_proxy_exc(z, w, r)
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
		//			http.Error(w, "BAD", http_status_500_internal_server_error)
		//		}
		//	}()
		http.Redirect(w, r, "./ui/index.html", http.StatusSeeOther)
	})

	z.router.HandleFunc("GET /ui/index.html", func(w http.ResponseWriter, r *http.Request) {
		defer handle_proxy_exc(z, w, r)
		var _ = return_ui_script(z, w, r, "ui/index.html")
	})

	z.router.HandleFunc("GET /ui2/index.html", func(w http.ResponseWriter, r *http.Request) {
		defer handle_proxy_exc(z, w, r)
		var _ = return_ui_script(z, w, r, "ui2/index.html")
	})

	z.router.HandleFunc("GET /ui/", func(w http.ResponseWriter, r *http.Request) {
		defer handle_proxy_exc(z, w, r)
		var _ = return_file(z, w, r, r.URL.Path, &efs1)
	})

	z.router.HandleFunc("GET /ui2/", func(w http.ResponseWriter, r *http.Request) {
		defer handle_proxy_exc(z, w, r)
		var _ = return_file(z, w, r, r.URL.Path, &efs2)
	})

	z.router.HandleFunc("GET /user-info", func(w http.ResponseWriter, r *http.Request) {
		logger.debug("Reg.GET /user-info")
		defer handle_proxy_exc(z, w, r)
		var _ = return_user_info(z, w, r)
	})

	z.router.HandleFunc("GET /pool", func(w http.ResponseWriter, r *http.Request) {
		defer handle_proxy_exc(z, w, r)
		var _ = list_pool_and_return_response(z, w, r, "")
	})

	z.router.HandleFunc("GET /pool/{pool}", func(w http.ResponseWriter, r *http.Request) {
		defer handle_proxy_exc(z, w, r)
		var pool = r.PathValue("pool")
		var _ = list_pool_and_return_response(z, w, r, pool)
	})

	// A POST request makes a pool.

	z.router.HandleFunc("POST /pool", func(w http.ResponseWriter, r *http.Request) {
		defer handle_proxy_exc(z, w, r)
		var _ = make_pool_and_return_response(z, w, r)
	})

	z.router.HandleFunc("DELETE /pool/{pool}", func(w http.ResponseWriter, r *http.Request) {
		defer handle_proxy_exc(z, w, r)
		var pool = r.PathValue("pool")
		var _ = delete_pool_and_return_response(z, w, r, pool)
	})

	// A PUT request makes a bucket.

	z.router.HandleFunc("PUT /pool/{pool}/bucket", func(w http.ResponseWriter, r *http.Request) {
		defer handle_proxy_exc(z, w, r)
		var pool = r.PathValue("pool")
		var _ = make_bucket_and_return_response(z, w, r, pool)
	})

	z.router.HandleFunc("DELETE /pool/{pool}/bucket/{bucket}", func(w http.ResponseWriter, r *http.Request) {
		defer handle_proxy_exc(z, w, r)
		var pool = r.PathValue("pool")
		var bucket = r.PathValue("bucket")
		var _ = delete_bucket_and_return_response(z, w, r, pool, bucket)
	})

	// A POST request makes a secret.

	z.router.HandleFunc("POST /pool/{pool}/secret", func(w http.ResponseWriter, r *http.Request) {
		defer handle_proxy_exc(z, w, r)
		var pool = r.PathValue("pool")
		var _ = make_secret_and_return_response(z, w, r, pool)
	})

	z.router.HandleFunc("DELETE /pool/{pool}/secret/{secret}", func(w http.ResponseWriter, r *http.Request) {
		defer handle_proxy_exc(z, w, r)
		var pool = r.PathValue("pool")
		var secret = r.PathValue("secret")
		var _ = delete_secret_and_return_response(z, w, r, pool, secret)
	})

	log.Printf("Reg(%s) start service", z.ep)
	for {
		var err1 = z.server.ListenAndServe()
		logger.infof("Reg ListenAndServe() done err=%v", err1)
	}
}

func handle_proxy_exc(z *registrar, w http.ResponseWriter, r *http.Request) {
	var x = recover()
	switch e := x.(type) {
	case nil:
	case *proxy_exc:
		fmt.Println("RECOVER!", e)
		http.Error(w, e.m, e.code)
	default:
		fmt.Println("TRAP unhandled panic", e)
		fmt.Println("stacktrace:\n" + string(debug.Stack()))
		http.Error(w, "BAD", http_status_500_internal_server_error)
	}
}

func return_ui_script(z *registrar, w http.ResponseWriter, r *http.Request, path string) *string {
	var data1, err1 = efs1.ReadFile(path)
	if err1 != nil {
		http.Error(w, "BAD", http_status_500_internal_server_error)
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
		http.Error(w, "BAD", http_status_500_internal_server_error)
		return nil
	}
	io.WriteString(w, string(data1))
	return &data1
}

// A "/user-info" request is assumed as the first request and it
// initializes the CSRF state.
func return_user_info(z *registrar, w http.ResponseWriter, r *http.Request) *user_info_response {
	var opr = "user-info"
	var u = grant_access_with_error_return(z, w, r, "", true)
	if u == nil {
		return nil
	}
	if !check_empty_arguments_with_error_return(z, w, r, "", opr) {
		return nil
	}

	var info = copy_user_record_to_ui(z, u)
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
	var poollist []*pool_data_ui
	for _, name := range namelist {
		var d = gather_pool_data(z.table, name)
		if d != nil && d.Owner_uid == u.Uid {
			poollist = append(poollist, copy_pool_data_to_ui(d))
		}
	}

	if pool != "" && len(poollist) == 0 {
		return_error_response(z, w, r, http_status_400_bad_request,
			[][2]string{
				message_No_pool,
				{"pool", pool},
			})
		return nil
	}
	if pool != "" && len(poollist) > 1 {
		logger.errf("Reg() multiple pools with the same id (pool=%s)",
			pool)
		return_error_response(z, w, r, http_status_500_internal_server_error,
			message_internal_error)
		return nil
	}

	slices.SortFunc(poollist, func(x, y *pool_data_ui) int {
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

func make_pool_and_return_response(z *registrar, w http.ResponseWriter, r *http.Request) *pool_data_response {
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
		return_error_response(z, w, r, http_status_400_bad_request,
			[][2]string{
				message_Buckets_directory_already_taken,
				{"path", path},
				{"owner", owner},
			})
		return nil
	}

	// Register secret for probing.

	var expiration = z.determine_expiration_time
	var secret = &secret_record{
		Pool:          pool,
		_access_key:   "",
		Secret_key:    generate_secret_key(),
		Secret_policy: secret_policy_internal_use,
		//Internal_use:      true,
		Expiration_time: expiration,
		Timestamp:       now,
	}
	var probe = set_with_unique_secret_key(z.table, secret)

	// Register pool.

	var newpool = &pool_record{
		Pool:              pool,
		Buckets_directory: path,
		Owner_uid:         u.Uid,
		Owner_gid:         args.Owner_gid,
		Probe_key:         probe,
		Online_status:     true,
		Expiration_time:   expiration,
		Timestamp:         now,
	}
	set_pool(z.table, pool, newpool)
	set_pool_state(z.table, pool, pool_state_INITIAL, pool_reason_NORMAL)
	var rspn = return_pool_data(z, w, r, pool)
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

	var d = gather_pool_data(z.table, pool)
	if d == nil {
		return_error_response(z, w, r, http_status_400_bad_request,
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
		var ok = delete_secret_key_unconditionally(z.table, k._access_key)
		if !ok {
			logger.infof("delete_secret_key failed (ignored)")
		}
	}

	// DOIT OR NOT DOIT: set none-policy to buckets for MinIO backend.

	//erase_backend_ep(self.tables, pool)
	//erase_pool_data(self.tables, pool)

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

func make_bucket_and_return_response(z *registrar, w http.ResponseWriter, r *http.Request, pool string) *pool_data_response {
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
	var bucket = args.Bucket
	var policy = intern_ui_bucket_policy(args.Bucket_policy)
	assert_fatal(policy != "")

	var now int64 = time.Now().Unix()
	var expiration = z.determine_expiration_time
	var desc = &bucket_record{
		Pool:            pool,
		Bucket:          bucket,
		Bucket_policy:   policy,
		Expiration_time: expiration,
		Timestamp:       now,
	}
	var ok1, holder = set_ex_bucket(z.table, bucket, desc)
	if !ok1 {
		var owner = find_owner_of_pool(z, holder)
		return_error_response(z, w, r, http_status_400_bad_request,
			[][2]string{
				message_Bucket_already_taken,
				{"owner", owner},
			})
		return nil
	}

	// MAKE BUCKET IN THE BACKEND.

	var rspn = return_pool_data(z, w, r, pool)
	return rspn
}

func delete_bucket_and_return_response(z *registrar, w http.ResponseWriter, r *http.Request, pool string, bucket string) *pool_data_response {
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
		return_error_response(z, w, r, http_status_404_not_found,
			[][2]string{
				message_No_bucket,
				{"bucket", bucket},
			})
		return nil
	}
	var rspn = return_pool_data(z, w, r, pool)
	return rspn
}

func make_secret_and_return_response(z *registrar, w http.ResponseWriter, r *http.Request, pool string) *pool_data_response {
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

	var expiration = z.determine_expiration_time
	var now = time.Now().Unix()
	var secret = &secret_record{
		Pool:            pool,
		_access_key:     "",
		Secret_key:      generate_secret_key(),
		Secret_policy:   policy,
		Expiration_time: expiration,
		Timestamp:       now,
	}
	var _ = set_with_unique_secret_key(z.table, secret)
	var rspn = return_pool_data(z, w, r, pool)
	return rspn
}

func delete_secret_and_return_response(z *registrar, w http.ResponseWriter, r *http.Request, pool string, secret string) *pool_data_response {
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
		return_error_response(z, w, r, http_status_400_bad_request,
			[][2]string{
				message_Bad_secret,
				{"secret", secret},
			})
		return nil
	}

	var rpsn *pool_data_response = return_pool_data(z, w, r, pool)
	return rpsn
}

// RETURN_POOL_DATA returns pool data.
func return_pool_data(z *registrar, w http.ResponseWriter, r *http.Request, pool string) *pool_data_response {
	var d = gather_pool_data(z.table, pool)
	assert_fatal(d != nil)
	var pooldata = copy_pool_data_to_ui(d)
	var rspn = &pool_data_response{
		response_common: response_common{
			Status:    "success",
			Reason:    nil,
			Timestamp: time.Now().Unix(),
		},
		Pool_data: pooldata,
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
	log_access(200, r)
	return
}

func return_error_response(z *registrar, w http.ResponseWriter, r *http.Request, code int, reason [][2]string) {
	var m = map[string]string{}
	for _, kv := range reason {
		m[kv[0]] = kv[1]
	}
	var rspn = &error_response{
		response_common: response_common{
			Status:    "error",
			Reason:    m,
			Timestamp: time.Now().Unix(),
		},
	}
	var b1, err1 = json.Marshal(rspn)
	assert_fatal(err1 == nil)
	http.Error(w, string(b1), code)
	log_access(code, r)
}

// VALIDATE_SESSION validates a session early.
func validate_session(z *registrar, w http.ResponseWriter, r *http.Request, agent http.Handler) {
	//	peer_addr = make_typical_ip_address(str(request.client.host))
	//	x_remote_user = request.headers.get("X-REMOTE-USER")
	//	user_id = _reg.map_claim_to_uid(x_remote_user)
	//	client = request.headers.get("X-REAL-IP")
	//	access_synopsis = [client, user_id, request.method, request.url]
	//	now = int(time.time())
	//	if peer_addr not in _reg.trusted_proxies {
	//		logger.error(f"Untrusted proxy: proxy={peer_addr};"
	//			f" Check trusted_proxies in configuration")
	//		body = {"status": "error",
	//			"reason": f"Configuration error (call administrator)",
	//			"time": str(now)}
	//		code = status.HTTP_403_FORBIDDEN
	//		log_access(f"{code}", *access_synopsis)
	//		time.sleep(_reg._bad_response_delay)
	//		response = JSONResponse(status_code=code, content=body)
	//		return response
	//	}
	//	if not _reg.check_user_is_registered(user_id) {
	//		logger.error(f"Access by an unregistered user:"
	//			f" uid={user_id}, x_remote_user={x_remote_user}")
	//		body = {"status": "error",
	//			"reason": f"Unregistered user: user={user_id}",
	//			"time": str(now)}
	//		code = status.HTTP_401_UNAUTHORIZED
	//		log_access(f"{code}", *access_synopsis)
	//		time.sleep(_reg._bad_response_delay)
	//		response = JSONResponse(status_code=code, content=body)
	//		return response
	//	}
	//	response = await call_next(request)
	//	return response
	//    except Exception as e {
	//        m = rephrase_exception_message(e)
	//        logger.error(f"Reg GOT AN UNHANDLED EXCEPTION: ({m})",
	//			exc_info=True)
	//        time.sleep(_reg._bad_response_delay)
	//        response = _make_status_500_response(m)
	//        return response
	//	}
	agent.ServeHTTP(w, r)
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

	if ensure_lens3_is_running(z.table) {
		logger.errf("Reg() lens3 is not running")
		return_error_response(z, w, r, http_status_500_internal_server_error,
			[][2]string{
				message_Lens3_not_running,
			})
		return nil
	}

	// Check on the frontend proxy.

	//var client = r.Header.Get("X-Real-Ip")
	var proxy = r.RemoteAddr
	if !check_frontend_proxy_trusted(z, proxy) {
		logger.errf("Reg() frontend proxy is untrusted: proxy=(%v)", proxy)
		return_error_response(z, w, r, http_status_500_internal_server_error,
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
		return_error_response(z, w, r, http_status_401_unauthorized,
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
			return_error_response(z, w, r, http_status_401_unauthorized,
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
		return_error_response(z, w, r, http_status_401_unauthorized,
			[][2]string{
				message_Bad_pool,
				{"pool", pool},
			})
		return nil
	}

	var poolprop = get_pool(z.table, pool)
	if poolprop == nil {
		logger.debugf("Reg() No pool: uid=(%s) pool=(%s)", uid, pool)
		return_error_response(z, w, r, http_status_401_unauthorized,
			[][2]string{
				message_No_pool,
				{"pool", pool},
			})
		return nil
	}
	if poolprop.Owner_uid != u.Uid {
		logger.debugf("Reg() Not pool owner: uid=(%s) pool=(%s)", uid, pool)
		return_error_response(z, w, r, http_status_401_unauthorized,
			[][2]string{
				message_Not_pool_owner,
				{"pool", pool},
			})
		return nil
	}

	var check_pool_state = false //AHOAHOAHO
	if pool != "" && check_pool_state {
		if ensure_pool_state(z.table, pool) {
			//return nil
		}
	}
	return u
}

// CHECK_USER_ACCOUNT checks the user account is active.  It may
// register a new user record, when it is the first session under
// default-allow setting (i.e., conf.User_approval=allow).
func check_user_account(z *registrar, uid string, firstsession bool) *user_record {
	// Reject unregistered users.

	var conf = &z.Registrar
	var approving = (conf.User_approval == user_default_allow && firstsession)
	var ui = get_user(z.table, uid)
	if !approving && ui == nil {
		return nil
	}

	// Reject users without local accounts.  It is weird,
	// authenticated users without local accounts.

	var uu, err1 = user.Lookup(uid)
	if err1 != nil {
		switch err1.(type) {
		case user.UnknownUserError:
		default:
		}
		logger.errf("Reg() user.Lookup(%s) fails: err=(%v)", uid, err1)
		return nil
	}

	// Check if the user is enabled.

	var now int64 = time.Now().Unix()
	if ui != nil {
		if !ui.Enabled || ui.Expiration_time < now {
			return nil
		} else {
			extend_user_expiration_time(z, ui)
			return ui
		}
	}

	// Regiter a new user record.

	assert_fatal(ui == nil && approving)

	if conf.Claim_uid_map == claim_uid_map_map {
		logger.errf("Reg() configuration error:"+
			" user_approval=%s claim_uid_map=%s",
			conf.User_approval, conf.Claim_uid_map)
		return nil
	}

	var uid_n, err2 = strconv.Atoi(uu.Uid)
	if err2 != nil {
		logger.errf("Reg() user.Lookup(%s) returns non-numeric uid=(%s)",
			uid, uu.Uid)
		return nil
	}
	if len(conf.Uid_allow_range_list) != 0 {
		if !check_int_in_ranges(uid_n, conf.Uid_allow_range_list) {
			logger.infof("Reg() a new user blocked: uid=(%s)", uid)
			return nil
		}
	}
	if check_int_in_ranges(uid_n, conf.Uid_block_range_list) {
		logger.infof("Reg() a new user blocked: uid=(%s)", uid)
		return nil
	}

	var gids, err3 = uu.GroupIds()
	if err3 != nil {
		logger.errf("Reg() user.GroupIds(%s) failed: err=(%v)", uid, err3)
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
	if len(groups) == 0 {
		logger.infof("no groups for a new user: uid=(%s)", uid)
		return nil
	}

	logger.infof("Reg() registering a new user: uid=(%s)", uid)

	// It doesn't care races...

	var days = ITE(conf.User_expiration_days != 0,
		conf.User_expiration_days, 365)
	var expiration = time.Now().AddDate(0, 0, days).Unix()
	var newuser = &user_record{
		Uid:                        uid,
		Claim:                      "",
		Groups:                     groups,
		Enabled:                    true,
		Expiration_time:            expiration,
		Check_terms_and_conditions: false,
		Timestamp:                  now,
	}
	set_user_force(z.table, newuser)
	return newuser
}

func check_frontend_proxy_trusted(z *registrar, proxy string) bool {
	var conf = &z.Registrar
	_ = conf
	var host, _, err1 = net.SplitHostPort(proxy)
	if err1 != nil {
		logger.warnf("bad r.RemoteAddr=(%s): err=(%v)", proxy, err1)
		return false
	}
	var ips, err2 = net.LookupIP(host)
	if err2 != nil {
		logger.warnf("net.LookupIP(%s) failed: err=(%v)", host, err2)
		return false
	}
	for _, ip := range ips {
		if slices.IndexFunc(z.trusted_proxies, ip.Equal) != -1 {
			return true
		}
	}
	return false
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
	set_csrf_token(z.table, uid, data)
	set_csrf_token_expiry(z.table, uid, int64(conf.Ui_session_duration))
	//var x = get_csrf_token(z.table, uid)
	//fmt.Println("make_csrf_tokens=", x)

	return data
}

func check_pool_owner__(t *keyval_table, uid string, pool string) bool {
	var poolprop = get_pool(t, pool)
	if poolprop != nil && poolprop.Owner_uid == uid {
		return true
	} else {
		return false
	}
}

// CHECK_MAKE_POOL_ARGUMENTS checks the entires of buckets_directory
// and owner_gid.  It normalizes the path of a buckets-directory (in
// the posix sense).
func check_make_pool_arguments(z *registrar, u *user_record, pool string, data any) reg_message {
	var args, ok = data.(*make_pool_arguments)
	if !ok {
		panic("(internal)")
	}
	// Check bucket-directory path.
	var bd = args.Buckets_directory
	var path = filepath.Clean(bd)
	if !filepath.IsAbs(path) {
		return reg_message{
			message_Bad_buckets_directory,
			{"path", bd},
		}
	}
	args.Buckets_directory = path
	// Check GID.  UID is not in the arguments.
	var groups = u.Groups
	var gid = args.Owner_gid
	if slices.Index(groups, gid) == -1 {
		return reg_message{
			message_Bad_group,
			{"group", gid},
		}
	}
	return nil
}

func check_make_bucket_arguments(z *registrar, u *user_record, pool string, data any) reg_message {
	var args, ok = data.(*make_bucket_arguments)
	if !ok {
		panic("(internal)")
	}
	// Check Bucket.
	if !check_bucket_naming(args.Bucket) {
		return reg_message{
			message_Bad_bucket,
			{"bucket", args.Bucket},
		}
	}
	// Check Bucket_policy.
	if slices.Index(bucket_policy_ui_list, args.Bucket_policy) == -1 {
		return reg_message{
			message_Bad_policy,
			{"policy", args.Bucket_policy},
		}
	}
	return nil
}

func check_make_secret_arguments(z *registrar, u *user_record, pool string, data any) reg_message {
	var args, ok = data.(*make_secret_arguments)
	if !ok {
		panic("(internal)")
	}
	// Check Secret_policy.
	if slices.Index(secret_policy_ui_list, args.Secret_policy) == -1 {
		return reg_message{
			message_Bad_policy,
			{"policy", args.Secret_policy},
		}
	}
	// Check Expiration_time. int64  `json:"expiration_time"`
	var now = time.Now()
	var e = time.Unix(args.Expiration_time, 0)
	var days = 365
	if !(e.After(now.AddDate(0, 0, -1)) && e.Before(now.AddDate(0, 0, days))) {
		return reg_message{
			message_Bad_expiration,
			{"expiration", e.Format(time.DateOnly)},
		}
	}
	return nil
}

func check_bucket_naming_with_error_return(z *registrar, w http.ResponseWriter, r *http.Request, bucket string) bool {
	var ok = check_bucket_naming(bucket)
	if !ok {
		return_error_response(z, w, r, http_status_400_bad_request,
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
		return_error_response(z, w, r, http_status_400_bad_request,
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
		return_error_response(z, w, r, http_status_400_bad_request,
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
		return_error_response(z, w, r, http_status_404_not_found,
			[][2]string{
				message_No_bucket,
				{"bucket", bucket},
			})
		return false
	}
	if b.Pool != pool {
		return_error_response(z, w, r, http_status_401_unauthorized,
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
		return_error_response(z, w, r, http_status_404_not_found,
			[][2]string{
				message_No_secret,
				{"secret", secret},
			})
		return false
	}
	if b.Pool != pool {
		return_error_response(z, w, r, http_status_401_unauthorized,
			[][2]string{
				message_Not_secret_owner,
				{"secret", secret},
			})
		return false
	}
	return true
}

type checker_fn func(z *registrar, u *user_record, pool string, data any) reg_message

func decode_request_body_with_error_return(z *registrar, w http.ResponseWriter, r *http.Request, u *user_record, pool string, opr string, data any, check checker_fn) bool {
	var ok1 = decode_request_body(z, r, data)
	if !ok1 {
		return_error_response(z, w, r, http_status_400_bad_request,
			[][2]string{
				message_Bad_body_encoding,
				{"op", opr},
			})
		return false
	}
	var msg = check(z, u, pool, data)
	if msg != nil {
		return_error_response(z, w, r, http_status_400_bad_request,
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

func copy_user_record_to_ui(z *registrar, u *user_record) *user_info_ui {
	var v = &user_info_ui{
		Reg_version:   z.Version,
		Uid:           u.Uid,
		Groups:        u.Groups,
		Lens3_version: lens3_version,
		S3_url:        z.UI.S3_url,
		Footer_banner: z.UI.Footer_banner,
	}
	return v
}

func copy_pool_data_to_ui(d *pool_data) *pool_data_ui {
	var v = &pool_data_ui{
		// POOL_RECORD
		Pool:              d.pool_record.Pool,
		Buckets_directory: d.Buckets_directory,
		Owner_uid:         d.Owner_uid,
		Owner_gid:         d.Owner_gid,
		Probe_key:         d.Probe_key,
		Online_status:     d.Online_status,
		Expiration_time:   d.pool_record.Expiration_time,
		Timestamp:         d.pool_record.Timestamp,
		// POOL_DATA
		Buckets: copy_bucket_desc_to_ui(d.Buckets),
		Secrets: copy_secret_desc_to_ui(d.Secrets),
		// USER_RECORD
		User_enabled_status: d.Enabled,
		// POOL_STATE_RECORD
		Backend_state:  d.State,
		Backend_reason: d.Reason,
	}
	return v
}

func copy_bucket_desc_to_ui(m []*bucket_record) []*bucket_desc_ui {
	var buckets []*bucket_desc_ui
	for _, d := range m {
		var u = &bucket_desc_ui{
			Pool:          d.Pool,
			Bucket:        d.Bucket,
			Bucket_policy: d.Bucket_policy,
			Timestamp:     d.Timestamp,
		}
		buckets = append(buckets, u)
	}
	return buckets
}

func copy_secret_desc_to_ui(m []*secret_record) []*secret_desc_ui {
	var secrets []*secret_desc_ui
	for _, d := range m {
		if d.Secret_policy == secret_policy_internal_use {
			continue
		}
		var u = &secret_desc_ui{
			Pool:            d.Pool,
			Access_key:      d._access_key,
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
	var poolprop = get_pool(z.table, pool)
	if poolprop == nil {
		return "unknown-user"
	}
	return poolprop.Owner_uid
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
	case bucket_policy_ui_UPLOAD:
		return bucket_policy_UPLOAD
	case bucket_policy_ui_DOWNLOAD:
		return bucket_policy_DOWNLOAD
	case bucket_policy_ui_PUBLIC:
		return bucket_policy_PUBLIC
	default:
		return ""
	}
}

func extend_user_expiration_time(z *registrar, ui *user_record) {
	var conf = &z.Registrar
	var days = ITE(conf.User_expiration_days != 0,
		conf.User_expiration_days, 365)
	var expiration = time.Now().AddDate(0, 0, days).Unix()
	if ui.Expiration_time < expiration {
		ui.Expiration_time = expiration
	}
	set_user_force(z.table, ui)
}

//(rtoken, stoken) = csrf_protect.generate_csrf_tokens()
//csrf_protect.set_csrf_cookie(stoken, response)
