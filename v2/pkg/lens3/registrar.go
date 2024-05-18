/* Lens3-Reg.  It is a registrar of buckets and secrets. */

// Copyright 2022-2024 RIKEN R-CCS
// SPDX-License-Identifier: BSD-2-Clause

package lens3

// UI expects the return as FastAPI/Starlette's "JSONResponse".
//
// media_type = "application/json"
// json.dumps(
//   content,
//   ensure_ascii=False,
//   allow_nan=False,
//   indent=None,
//   separators=(",", ":"),
// ).encode("utf-8")

// ??? NOTE: Maybe, consider adding a "Retry-After" header for 503 error.

// ??? For CSRF prevention, this uses a "double submit cookie" as specified
// by fastapi_csrf_protect.  It uses a cookie "fastapi-csrf-token" and
// a header "X-CSRF-Token" (the names are fixed).  The CSRF state is
// initialized in getting user_info.  See
// https://github.com/aekasitt/fastapi-csrf-protect.

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
	"slices"
	"strconv"
	"strings"
	"time"
	//"runtime"
)

import "embed"

//go:embed ui
var efs1 embed.FS

//go:embed ui2
var efs2 embed.FS

//{policy: "readwrite", keys: pool_data.secrets_rw},
//{policy: "readonly", keys: pool_data.secrets_ro},
//{policy: "writeonly", keys: pool_data.secrets_wo},

type registrar struct {
	table *keyval_table

	server *http.Server
	router *http.ServeMux

	determine_expiration_time int64

	*reg_conf
	//registrar_conf
}

type response_to_ui interface{ response_union() }

func (*pool_desc_response) response_union() {}
func (*user_info_response) response_union() {}

// XXX_RESPONSE is a json format of a response to UI.  See the
// function set_pool_data() in "v1/ui/src/lens3c.ts".  Status is
// "success" or "error".
type response_common struct {
	Status       string `json:"status"`
	Reason       string `json:"reason"`
	X_csrf_token string `json:"x_csrf_token"`
	Timestamp    int64  `json:"time"`
}

type success_response struct {
	response_common
}

type error_response struct {
	response_common
}

type user_info_response struct {
	response_common
	User_info user_info_ui `json:"user_info"`
}

type pool_desc_response struct {
	response_common
	Pool_desc *pool_desc_ui `json:"pool_desc"`
}

type pool_list_response struct {
	response_common
	Pool_list []*pool_desc_ui `json:"pool_list"`
}

type pool_desc_ui struct {
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
	Modification_time   int64             `json:"modification_time"`
}

type bucket_desc_ui struct {
	Pool              string        `json:"pool"`
	Bucket            string        `json:"name"`
	Bucket_policy     bucket_policy `json:"bkt_policy"`
	Modification_time int64         `json:"modification_time"`
}

type secret_desc_ui struct {
	Pool              string        `json:"owner"`
	Access_key        string        `json:"access_key"`
	Secret_key        string        `json:"secret_key"`
	Secret_policy     secret_policy `json:"secret_policy"`
	Expiration_time   int64         `json:"expiration_time"`
	Modification_time int64         `json:"modification_time"`
}

type user_info_ui struct {
	Reg_version   string   `json:"reg_version"`
	Uid           string   `json:"uid"`
	Groups        []string `json:"groups"`
	Lens3_version string   `json:"lens3_version"`
	S3_url        string   `json:"s3_url"`
	Footer_banner string   `json:"footer_banner"`
}

type empty_request struct{}

type make_pool_request struct {
	Buckets_directory string `json:"buckets_directory"`
	Owner_gid         string `json:"owner_gid"`
}

type make_bucket_request struct {
	Bucket        string `json:"name"`
	Bucket_policy string `json:"bkt_policy"`
}

type make_secret_request struct {
	Secret_policy   string `json:"key_policy"`
	Expiration_time int64  `json:"expiration_time"`
}

var the_registrar = registrar{}

var err_body_not_allowed = errors.New("http: request method or response status code does not allow body")

const (
	secret_policy_ui_READWRITE string = "readwrite"
	secret_policy_ui_READONLY  string = "readonly"
	secret_policy_ui_WRITEONLY string = "writeonly"
)

const (
	bucket_policy_ui_NONE     string = "none"
	bucket_policy_ui_UPLOAD   string = "upload"
	bucket_policy_ui_DOWNLOAD string = "download"
	bucket_policy_ui_PUBLIC   string = "public"
)

var (
	message_Missing_or_bad_pool_id = [2]string{"message",
		"Missing or bad pool id"}
	message_Missing_or_bad_bucket = [2]string{"message",
		"Missing or bad bucket"}
	message_Missing_or_bad_secret = [2]string{"message",
		"Missing or bad secret"}
	message_No_pool = [2]string{"message",
		"No pool"}
	message_No_bucket = [2]string{"message",
		"No bucket"}
	message_Arguments_not_empty = [2]string{"message",
		"Arguments not empty"}
	message_Bad_arguments = [2]string{"message",
		"Bad arguments"}
)

func configure_registrar(z *registrar, t *keyval_table, conf *reg_conf) {
	z.table = t
	z.reg_conf = conf
}

func start_registrar(z *registrar) {
	fmt.Println("start_registrar() z=", z)
	z.router = http.NewServeMux()
	var port = z.Registrar.Port
	var ep = net.JoinHostPort("", strconv.Itoa(port))
	z.server = &http.Server{
		Addr:    ep,
		Handler: z.router,
	}

	// Root "/" requests are redirected.

	z.router.HandleFunc("GET /{$}", func(w http.ResponseWriter, r *http.Request) {
		defer handle_proxy_exc(z, w, r)
		logger.debug("REG.GET /")
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

	z.router.HandleFunc("GET /ui/index.html/{$}", func(w http.ResponseWriter, r *http.Request) {
		defer handle_proxy_exc(z, w, r)
		return_ui_script(z, w, r, "ui/index.html")
	})

	z.router.HandleFunc("GET /ui2/index.html/{$}", func(w http.ResponseWriter, r *http.Request) {
		defer handle_proxy_exc(z, w, r)
		return_ui_script(z, w, r, "ui2/index.html")
	})

	z.router.HandleFunc("GET /ui/", func(w http.ResponseWriter, r *http.Request) {
		defer handle_proxy_exc(z, w, r)
		return_file(z, w, r, r.URL.Path, &efs1)
	})

	z.router.HandleFunc("GET /ui2/", func(w http.ResponseWriter, r *http.Request) {
		defer handle_proxy_exc(z, w, r)
		return_file(z, w, r, r.URL.Path, &efs2)
	})

	// A "/user-info" request is assumed as the first request and it
	// initializes the CSRF state.

	z.router.HandleFunc("GET /user-info/{$}", func(w http.ResponseWriter, r *http.Request) {
		defer handle_proxy_exc(z, w, r)
		//var x_remote_user = r.Header.Get("X_Remote_User")
		//var x_real_ip = r.Header.Get("X_Real_Ip")
		//_, _ = x_remote_user, x_real_ip
		var uid = "???"
		//grant_access(z, uid, nil, false)
		var u = get_user(z.table, uid)
		if u == nil {
			u = &user_record{
				Uid:                        "AHOAHOAHO",
				Claim:                      "",
				Groups:                     []string{"boo1", "hoo2", "woo2"},
				Enabled:                    true,
				Blocked:                    true,
				Expiration_time:            10,
				Check_terms_and_conditions: true,
				Modification_time:          20,
			}
		}
		var info = &user_info_ui{
			Reg_version:   z.Version,
			Uid:           u.Uid,
			Groups:        u.Groups,
			Lens3_version: lens3_version,
			S3_url:        z.UI.S3_url,
			Footer_banner: z.UI.Footer_banner,
		}
		var rspn = &user_info_response{
			response_common: response_common{
				Status:       "success",
				Reason:       "",
				X_csrf_token: "???",
				Timestamp:    time.Now().Unix(),
			},
			User_info: *info,
		}
		var v1, err1 = json.Marshal(rspn)
		if err1 != nil {
			panic(err1)
		}
		io.WriteString(w, string(v1))
		log_access(200, r)
	})

	z.router.HandleFunc("GET /pool/{$}", func(w http.ResponseWriter, r *http.Request) {
		defer handle_proxy_exc(z, w, r)
		var x_remote_user = r.Header.Get("X_Remote_User")
		var x_real_ip = r.Header.Get("X_Real_Ip")
		_ = x_remote_user
		_ = x_real_ip
		//var uid = map_claim_to_uid(z, x_remote_user)
		//grant_access(z, uid, None, False)
		var uid = "matu"
		var _ = return_list_pools_of_user(z, w, r, uid, "*")
	})

	// A POST request makes a pool.

	z.router.HandleFunc("POST /pool/{$}", func(w http.ResponseWriter, r *http.Request) {
		defer handle_proxy_exc(z, w, r)
		//csrf_protect.validate_csrf(r)
		//var uid = map_claim_to_uid(z, x_remote_user)
		//grant_access(z, uid, None, False)
		var _ *pool_desc_response = make_new_pool_and_return_response(z, w, r)
	})

	z.router.HandleFunc("GET /pool/{pool}/{$}", func(w http.ResponseWriter, r *http.Request) {
		defer handle_proxy_exc(z, w, r)
		//var uid = map_claim_to_uid(z, x_remote_user)
		//grant_access(uid, None, False)
		var uid = "AHOAHOAHO"
		var pool = r.PathValue("pool")
		if !check_pool_naming_with_error_return(z, w, r, pool) {
			return
		}
		var _ = return_list_pools_of_user(z, w, r, uid, pool)
	})

	z.router.HandleFunc("DELETE /pool/{pool}/{$}", func(w http.ResponseWriter, r *http.Request) {
		defer handle_proxy_exc(z, w, r)
		//csrf_protect.validate_csrf(r)
		//var uid = map_claim_to_uid(z, x_remote_user)
		//grant_access(z, uid, None, False)
		var pool = r.PathValue("pool")
		if !check_pool_naming_with_error_return(z, w, r, pool) {
			return
		}
		var _ = delete_pool_and_return_response(z, w, r, pool)
	})

	// A PUT request makes a bucket.

	z.router.HandleFunc("PUT /pool/{pool}/bucket/{$}", func(w http.ResponseWriter, r *http.Request) {
		defer handle_proxy_exc(z, w, r)
		var pool = r.PathValue("pool")
		if !check_pool_naming_with_error_return(z, w, r, pool) {
			return
		}
		var _ = make_bucket_and_return_response(z, w, r, pool)
	})

	z.router.HandleFunc("DELETE /pool/{pool}/bucket/{bucket}/{$}", func(w http.ResponseWriter, r *http.Request) {
		defer handle_proxy_exc(z, w, r)
		var pool = r.PathValue("pool")
		if !check_pool_naming_with_error_return(z, w, r, pool) {
			return
		}
		var bucket = r.PathValue("bucket")
		if !check_bucket_naming_with_error_return(z, w, r, bucket) {
			return
		}

		var err1 = delete_bucket_unconditionally(z.table, bucket)
		if err1 != nil {
			return_error_response(z, w, r, http_status_404_not_found,
				[][2]string{
					message_No_bucket,
					{"pool", pool},
					{"bucket", bucket},
				})
			return
		}
		var _ *pool_desc_response = return_pool_data(z, w, r, pool)
	})

	// A POST request makes a secret.

	z.router.HandleFunc("POST /pool/{pool}/secret/{$}", func(w http.ResponseWriter, r *http.Request) {
		defer handle_proxy_exc(z, w, r)
		var pool = r.PathValue("pool")
		if !check_pool_naming_with_error_return(z, w, r, pool) {
			return
		}

		var makesecret make_secret_request
		var ok1 = decode_request_body(z, r, &makesecret)
		if !ok1 {
			return_error_response(z, w, r, http_status_400_bad_request,
				[][2]string{
					message_Bad_arguments,
					{"op", "make-secret"},
					{"pool", pool},
				})
			return
		}

		var policy = intern_ui_secret_policy(makesecret.Secret_policy)
		if policy == "" {
			return_error_response(z, w, r, http_status_400_bad_request,
				[][2]string{
					message_Bad_arguments,
					{"op", "make-secret"},
					{"policy", makesecret.Secret_policy},
				})
			return
		}

		var expiration = z.determine_expiration_time
		var now = time.Now().Unix()
		var secret = &secret_record{
			Pool:              pool,
			_access_key:       "",
			Secret_key:        generate_secret_key(),
			Secret_policy:     policy,
			Expiration_time:   expiration,
			Modification_time: now,
		}
		var _ = set_with_unique_access_key(z.table, secret)
		var _ *pool_desc_response = return_pool_data(z, w, r, pool)
	})

	z.router.HandleFunc("DELETE /pool/{pool}/secret/{secret}/{$}", func(w http.ResponseWriter, r *http.Request) {
		defer handle_proxy_exc(z, w, r)
		var pool = r.PathValue("pool")
		if !check_pool_naming_with_error_return(z, w, r, pool) {
			return
		}
		var secret = r.PathValue("secret")
		if !check_access_key_naming_with_error_return(z, w, r, secret) {
			return
		}

		//grant_access(uid, pool, false)
		//ensure_secret_owner_only(self.tables, access_key, pool_id)
		var err2 = delete_secret_key_unconditionally(z.table, secret)
		if err2 != nil {
			logger.infof("delete_secret_key failed (ignored): err=(%v)", err2)
			return_error_response(z, w, r, http_status_400_bad_request,
				[][2]string{
					message_Missing_or_bad_secret,
					{"secret", secret},
				})
			return
		}

		var _ *pool_desc_response = return_pool_data(z, w, r, pool)
	})

	log.Println("Reg start service")
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
		fmt.Println("RECOVER!", e)
		fmt.Println("stacktrace:\n" + string(debug.Stack()))
		http.Error(w, "BAD", http_status_500_internal_server_error)
	}
}

// VALIDATE_SESSION validates a session early.  (Note it performs
// mapping of a user-id twice, once here and once later).
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

// GRANT_ACCESS checks an access to a pool by a user is granted.  It
// does not check the pool-state on deleting a pool.
func grant_access(z *registrar, uid string, pool string, check_pool_state bool) bool {
	if ensure_lens3_is_running(z.table) {
		return false
	}
	if ensure_user_is_active(z.table, uid, z.Registrar.User_approval) {
		return false
	}
	if pool != "" {
		if ensure_pool_owner(z.table, pool, uid) {
			return false
		}
	}
	if pool != "" && check_pool_state {
		if ensure_pool_state(z.table, pool, z.Registrar.User_approval) {
			return false
		}
	}
	return true
}

func ensure_pool_owner(t *keyval_table, pool string, uid string) bool {
	var pooldesc = get_pool(t, pool)
	if pooldesc != nil && pooldesc.Owner_uid == uid {
		return true
	} else {
		return false
	}
}

func decode_request_body(z *registrar, r *http.Request, data any) bool {
	// r.Body : io.ReadCloser.
	var d = json.NewDecoder(r.Body)
	d.DisallowUnknownFields()
	var err1 = d.Decode(data)
	if err1 != nil {
		return false
	}
	if !check_fields_filled(data) {
		return false
	}
	// Check EOF.  Garbage data means an error.
	var is = d.Buffered()
	var _, err2 = is.Read([]byte{9})
	if err2 == nil {
		return false
	}
	return true
}

// RETURN_LIST_POOLS_OF_USER lists pools owned by a user if passed "*"
// for pool-name.  Or, it returns information of the pool given a
// pool-name.
func return_list_pools_of_user(z *registrar, w http.ResponseWriter, r *http.Request, uid string, pool string) *pool_list_response {
	var namelist = list_pools(z.table, pool)
	var poollist []*pool_desc_ui
	for _, name := range namelist {
		var d = gather_pool_desc(z.table, name)
		if d != nil && d.Owner_uid == uid {
			poollist = append(poollist, copy_pool_desc_to_ui(d))
		}
	}

	if pool != "*" && len(poollist) == 0 {
		return_error_response(z, w, r, http_status_400_bad_request,
			[][2]string{
				message_No_pool,
				{"pool", pool},
			})
		return nil
	}
	if pool != "*" && len(poollist) > 1 {
		logger.errorf("Reg inconsistency; multiple pools (pool=%s)",
			pool)
		return_error_response(z, w, r, http_status_500_internal_server_error,
			[][2]string{
				{"message", "(internal: duplicate pool entries)"},
			})
		return nil
	}

	slices.SortFunc(poollist, func(x, y *pool_desc_ui) int {
		return strings.Compare(x.Buckets_directory, y.Buckets_directory)
	})
	var rspn = &pool_list_response{
		response_common: response_common{
			Status:       "success",
			Reason:       "",
			X_csrf_token: "???",
			Timestamp:    time.Now().Unix(),
		},
		Pool_list: poollist,
	}
	var v1, err1 = json.Marshal(rspn)
	if err1 != nil {
		panic(err1)
	}
	io.WriteString(w, string(v1))
	log_access(200, r)
	return rspn
}

func map_claim_to_uid(z *registrar, x_remote_user string) string {
	return x_remote_user
}

func copy_pool_desc_to_ui(d *pool_desc) *pool_desc_ui {
	var u = pool_desc_ui{
		// POOL_RECORD
		Pool:              d.pool_record.Pool,
		Buckets_directory: d.Buckets_directory,
		Owner_uid:         d.Owner_uid,
		Owner_gid:         d.Owner_gid,
		Probe_key:         d.Probe_key,
		Online_status:     d.Online_status,
		Expiration_time:   d.pool_record.Expiration_time,
		Modification_time: d.pool_record.Modification_time,
		// POOL_DESC
		Buckets: copy_bucket_desc_to_ui(d.Buckets),
		Secrets: copy_secret_desc_to_ui(d.Secrets),
		// USER_RECORD
		User_enabled_status: d.Enabled,
		// POOL_STATE_RECORD
		Backend_state:  d.State,
		Backend_reason: d.Reason,
	}
	return &u
}

func copy_bucket_desc_to_ui(m []*bucket_record) []*bucket_desc_ui {
	var buckets []*bucket_desc_ui
	for _, d := range m {
		var u = &bucket_desc_ui{
			Pool:              d.Pool,
			Bucket:            d.Bucket,
			Bucket_policy:     d.Bucket_policy,
			Modification_time: d.Modification_time,
		}
		buckets = append(buckets, u)
	}
	return buckets
}

func copy_secret_desc_to_ui(m []*secret_record) []*secret_desc_ui {
	var secrets []*secret_desc_ui
	for _, d := range m {
		var u = &secret_desc_ui{
			Pool:              d.Pool,
			Access_key:        d._access_key,
			Secret_key:        d.Secret_key,
			Secret_policy:     d.Secret_policy,
			Expiration_time:   d.Expiration_time,
			Modification_time: d.Modification_time,
		}
		secrets = append(secrets, u)
	}
	return secrets
}

func return_ui_script(z *registrar, w http.ResponseWriter, r *http.Request, path string) {
	defer handle_proxy_exc(z, w, r)
	var data1, err1 = efs1.ReadFile(path)
	if err1 != nil {
		http.Error(w, "BAD", http_status_500_internal_server_error)
		return
	}
	var parameters = (`<script type="text/javascript">const base_path_="` +
		z.Registrar.Base_path + `";</script>`)
	var data2 = strings.Replace(string(data1),
		"PLACE_BASE_PATH_SETTING_HERE", parameters, 1)
	//fmt.Println(string(data2))
	io.WriteString(w, string(data2))
}

func return_file(z *registrar, w http.ResponseWriter, r *http.Request, path string, efs1 *embed.FS) {
	defer handle_proxy_exc(z, w, r)
	var data1, err1 = efs1.ReadFile(path)
	if err1 != nil {
		http.Error(w, "BAD", http_status_500_internal_server_error)
		return
	}
	io.WriteString(w, string(data1))
}

/* POOL-MAKING */

func make_new_pool_and_return_response(z *registrar, w http.ResponseWriter, r *http.Request) *pool_desc_response {
	var uid = "AHOAHOAHO"
	var makepool make_pool_request
	var ok1 = decode_request_body(z, r, &makepool)
	if !ok1 {
		http.Error(w, "BAD", http_status_400_bad_request)
		return nil
	}
	//z.table
	var expiration = z.determine_expiration_time
	if !grant_access(z, uid, "", false) {
		http.Error(w, "BAD", http_status_401_unauthorized)
		return nil
	}
	check_make_pool_arguments(z, uid, &makepool)
	var now int64 = time.Now().Unix()
	var poolname = &pool_mutex_record{
		Owner_uid:         uid,
		Modification_time: now,
	}
	var pool = set_with_unique_pool_name(z.table, poolname)
	var secret = &secret_record{
		Pool:              pool,
		_access_key:       "",
		Secret_key:        "",
		Secret_policy:     secret_policy_READWRITE,
		Expiration_time:   expiration,
		Modification_time: now,
	}
	var probe = set_with_unique_access_key(z.table, secret)
	var ok, holder = set_ex_buckets_directory(z.table, makepool.Buckets_directory, pool)
	if !ok {
		var _ = delete_pool_name_unconditionally(z.table, pool)
		var _ = delete_secret_key_unconditionally(z.table, probe)
		var owner = find_owner_of_pool(z, holder)
		raise(reg_error(400, fmt.Sprintf("Buckets-directory is already used:"+
			" path=(%s), holder=(%s)",
			makepool.Buckets_directory, owner)))
		return nil
	}
	set_pool_state(z.table, pool, pool_state_INITIAL, pool_reason_NORMAL)

	var rspn = return_pool_data(z, w, r, pool)
	return rspn
}

// CHECK_MAKE_POOL_ARGUMENTS checks the entires of buckets_directory
// and owner_gid.  It normalizes the path of a buckets-directory (in
// the posix sense).
func check_make_pool_arguments(z *registrar, uid string, makepool *make_pool_request) bool {
	var u = get_user(z.table, uid)
	if u == nil {
		return false
	}
	// Check GID.  UID is not in the arguments.
	var groups = u.Groups
	var gid = makepool.Owner_gid
	if slices.Index(groups, gid) == -1 {
		raise(reg_error(403, fmt.Sprintf("Bad group=%s", gid)))
	}
	// Check bucket-directory path.
	var bd = makepool.Buckets_directory
	var path = filepath.Clean(bd)
	if !filepath.IsAbs(path) {
		raise(reg_error(400, fmt.Sprintf("Buckets-directory is not absolute:"+
			" path=(%s)", bd)))
	}
	makepool.Buckets_directory = path
	return true
}

/* POOL-DELETION */

func delete_pool_and_return_response(z *registrar, w http.ResponseWriter, r *http.Request, pool string) *success_response {
	// activate_backend(pool)
	// disable_backend_secrets()
	// disable_backend_buckets()

	var d = gather_pool_desc(z.table, pool)

	// Delete buckets_directory.

	var err1 = delete_buckets_directory_unconditionally(z.table, d.Buckets_directory)
	if err1 != nil {
		logger.infof("delete_buckets_directory failed (ignored): err=(%v)", err1)
	}

	// Delete buckets.

	var bkts = list_buckets(z.table, pool)
	for _, b := range bkts {
		var err2 = delete_bucket_unconditionally(z.table, b.Bucket)
		if err2 != nil {
			logger.infof("delete_bucket failed (ignored): err=(%v)", err2)
		}
	}

	// Delete access-keys.

	for _, k := range d.Secrets {
		assert_fatal(k.Pool == pool)
		var err2 = delete_secret_key_unconditionally(z.table, k._access_key)
		if err2 != nil {
			logger.infof("delete_secret_key failed (ignored): err=(%v)", err2)
		}
	}

	// DOIT OR NOT DOIT: set none-policy to buckets for MinIO backend.

	//erase_backend_ep(self.tables, pool)
	//erase_pool_data(self.tables, pool)

	var rspn = &success_response{
		response_common: response_common{
			Status:       "success",
			Reason:       "",
			X_csrf_token: "???",
			Timestamp:    time.Now().Unix(),
		},
	}
	var v1, err3 = json.Marshal(rspn)
	if err3 != nil {
		panic(err3)
	}
	io.WriteString(w, string(v1))
	log_access(200, r)
	return rspn
}

func make_bucket_and_return_response(z *registrar, w http.ResponseWriter, r *http.Request, pool string) *pool_desc_response {
	var makebucket make_bucket_request
	var ok1 = decode_request_body(z, r, &makebucket)
	if !ok1 {
		http.Error(w, "BAD", http_status_400_bad_request)
		return nil
	}

	var bucket = makebucket.Bucket
	if !check_bucket_naming_with_error_return(z, w, r, bucket) {
		return nil
	}

	var policy = intern_ui_bucket_policy(makebucket.Bucket_policy)
	if policy == "" {
		return_error_response(z, w, r, http_status_400_bad_request,
			[][2]string{
				message_Bad_arguments,
				{"op", "make-bucket"},
				{"bucket-policy", makebucket.Bucket_policy},
			})
		return nil
	}

	var now int64 = time.Now().Unix()
	var expiration = z.determine_expiration_time
	var desc = &bucket_record{
		Pool:              pool,
		Bucket:            bucket,
		Bucket_policy:     policy,
		Expiration_time:   expiration,
		Modification_time: now,
	}
	var ok2, holder = set_ex_bucket(z.table, bucket, desc)
	if !ok2 {
		var owner = find_owner_of_pool(z, holder)
		raise(reg_error(403, fmt.Sprintf("Bucket name taken: owner=%s",
			owner)))
		return nil
	}

	var ok3 = make_bucket_in_backend(z, pool, &makebucket)
	_ = ok3
	var rspn = return_pool_data(z, w, r, pool)
	return rspn
}

func encode_error_message(keyvals [][2]string) string {
	var b bytes.Buffer
	b.Write([]byte("{"))
	for _, kv := range keyvals {
		var b1, err1 = json.Marshal(kv[0])
		assert_fatal(err1 != nil)
		var _, err2 = b.Write(b1)
		assert_fatal(err2 != nil)
		var _, err3 = b.Write([]byte(":"))
		assert_fatal(err3 != nil)
		var b2, err4 = json.Marshal(kv[1])
		assert_fatal(err4 != nil)
		var _, err5 = b.Write(b2)
		assert_fatal(err5 != nil)
		var _, err6 = b.Write([]byte(","))
		assert_fatal(err6 != nil)
	}
	return string(b.Bytes())
}

func return_error_response(z *registrar, w http.ResponseWriter, r *http.Request, code int, reason [][2]string) {
	var rspn = &error_response{
		response_common: response_common{
			Status:       "error",
			Reason:       encode_error_message(reason),
			X_csrf_token: "???",
			Timestamp:    time.Now().Unix(),
		},
	}
	var b1, err1 = json.Marshal(rspn)
	assert_fatal(err1 != nil)
	http.Error(w, string(b1), code)
	log_access(code, r)
}

// RETURN_POOL_DATA returns pool data.
func return_pool_data(z *registrar, w http.ResponseWriter, r *http.Request, pool string) *pool_desc_response {
	var d = gather_pool_desc(z.table, pool)
	assert_fatal(d != nil)
	var pooldesc = copy_pool_desc_to_ui(d)

	var rspn = &pool_desc_response{
		response_common: response_common{
			Status:       "success",
			Reason:       "",
			X_csrf_token: "???",
			Timestamp:    time.Now().Unix(),
		},
		Pool_desc: pooldesc,
	}
	var v1, err1 = json.Marshal(rspn)
	if err1 != nil {
		panic(err1)
	}

	io.WriteString(w, string(v1))
	log_access(200, r)
	return rspn
}

// FIND_OWNER_OF_POOL finds an owner of a pool for printing
// error messages.  It returns unknown-user, when an owner is not
// found.
func find_owner_of_pool(z *registrar, pool string) string {
	if pool == "" {
		return "unknown-user"
	}
	var pooldesc = get_pool(z.table, pool)
	if pooldesc == nil {
		return "unknown-user"
	}
	return pooldesc.Owner_uid
}

func intern_ui_secret_policy(policy string) secret_policy {
	switch policy {
	case secret_policy_ui_READWRITE:
		return secret_policy_READWRITE
	case secret_policy_ui_READONLY:
		return secret_policy_READONLY
	case secret_policy_ui_WRITEONLY:
		return secret_policy_WRITEONLY
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

func check_pool_naming_with_error_return(z *registrar, w http.ResponseWriter, r *http.Request, pool string) bool {
	var ok = check_pool_naming(pool)
	if !ok {
		return_error_response(z, w, r, http_status_400_bad_request,
			[][2]string{
				message_Missing_or_bad_pool_id,
				{"pool", pool},
			})
	}
	return ok
}

func check_bucket_naming_with_error_return(z *registrar, w http.ResponseWriter, r *http.Request, bucket string) bool {
	var ok = check_bucket_naming(bucket)
	if !ok {
		return_error_response(z, w, r, http_status_400_bad_request,
			[][2]string{
				message_Missing_or_bad_bucket,
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
				message_Missing_or_bad_secret,
				{"secret", secret},
			})
	}
	return ok
}

func check_empty_arguments_with_error_return(z *registrar, w http.ResponseWriter, r *http.Request, pool string) bool {
	var emptyrequest empty_request
	var ok = decode_request_body(z, r, &emptyrequest)
	if !ok {
		return_error_response(z, w, r, http_status_400_bad_request,
			[][2]string{
				message_Arguments_not_empty,
			})
	}
	return ok
}

//(rtoken, stoken) = csrf_protect.generate_csrf_tokens()
//csrf_protect.set_csrf_cookie(stoken, response)
