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

	*api_conf
	//registrar_conf
}

type response_to_ui interface{ response_union() }

func (*pool_desc_response) response_union() {}
func (*user_info_response) response_union() {}

// Status is "success" or "error".
type response_common struct {
	Status       string `json:"status"`
	Reason       string `json:"reason"`
	X_csrf_token string `json:"x_csrf_token"`
	Timestamp    int64  `json:"time"`
}

// POOL_DESC_RESPONSE is a json format of a response to UI.  See the
// function set_pool_data() in "v1/ui/src/lens3c.ts".
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
	Name              string     `json:"name"`
	Pool              string     `json:"pool"`
	Bkt_policy        bkt_policy `json:"bkt_policy"`
	Modification_time int64      `json:"modification_time"`
}

type secret_desc_ui struct {
	Access_key        string     `json:"access_key"`
	Secret_key        string     `json:"secret_key"`
	Pool              string     `json:"owner"`
	Key_policy        key_policy `json:"key_policy"`
	Expiration_time   int64      `json:"expiration_time"`
	Modification_time int64      `json:"modification_time"`
}

// user_info_response is a json format of a response to UI.
type user_info_response struct {
	response_common
	User_info user_info_ui `json:"user_info"`
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
	Buckets_directory string `json:"buckets_directory"`
	Owner_gid         string `json:"owner_gid"`
}

var the_registrar = registrar{}

var err_body_not_allowed = errors.New("http: request method or response status code does not allow body")

func configure_registrar(z *registrar, t *keyval_table, conf *api_conf) {
	z.table = t
	z.api_conf = conf
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

	z.router.HandleFunc("GET /{$}", func(w http.ResponseWriter, r *http.Request) {
		logger.debug("API.GET /")
		defer handle_proxy_exc(z, w, r)
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
		//var x_remote_user = r.Header.Get("X_Remote_User")
		//var x_real_ip = r.Header.Get("X_Real_Ip")
		//_, _ = x_remote_user, x_real_ip
		defer handle_proxy_exc(z, w, r)
		return_ui_script(z, w, r, "ui/index.html")
	})

	z.router.HandleFunc("GET /ui2/index.html", func(w http.ResponseWriter, r *http.Request) {
		//var x_remote_user = r.Header.Get("X_Remote_User")
		//var x_real_ip = r.Header.Get("X_Real_Ip")
		//_, _ = x_remote_user, x_real_ip
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

	// This returns a user information and initializes the CSRF state.
	z.router.HandleFunc("GET /user-info", func(w http.ResponseWriter, r *http.Request) {
		defer handle_proxy_exc(z, w, r)
		var uid = "???"
		//grant_access(z, uid, nil, false)
		var u = get_user(z.table, uid)
		if u == nil {
			u = &user_record{
				Uid:                        "aho",
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
			Api_version:   z.Version,
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

	z.router.HandleFunc("GET /pool", func(w http.ResponseWriter, r *http.Request) {
		var x_remote_user = r.Header.Get("X_Remote_User")
		var x_real_ip = r.Header.Get("X_Real_Ip")
		_ = x_remote_user
		_ = x_real_ip
		//var uid = map_claim_to_uid(z, x_remote_user)
		var uid = "matu"
		//grant_access(z, uid, None, False)
		var poollist1 = list_pools_of_user(z, uid, "*")
		var rspn = &pool_list_response{
			response_common: response_common{
				Status:       "success",
				Reason:       "",
				X_csrf_token: "???",
				Timestamp:    time.Now().Unix(),
			},
			Pool_list: poollist1,
		}
		var v1, err1 = json.Marshal(rspn)
		if err1 != nil {
			panic(err1)
		}
		io.WriteString(w, string(v1))
		log_access(200, r)
	})

	// Makes a pool.
	z.router.HandleFunc("POST /pool", func(w http.ResponseWriter, r *http.Request) {
		//csrf_protect.validate_csrf(r)
		var rspn *pool_desc_response = make_new_pool(z, w, r)
		if rspn == nil {
			// A response was already returned on an error.
			return
		}
		var v1, err1 = json.Marshal(rspn)
		if err1 != nil {
			panic(err1)
		}
		io.WriteString(w, string(v1))
		log_access(200, r)
	})

	z.router.HandleFunc("GET /pool/{pool}", func(w http.ResponseWriter, r *http.Request) {})

	z.router.HandleFunc("DELETE /pool/{pool}", func(w http.ResponseWriter, r *http.Request) {})

	// Make a bucket.
	z.router.HandleFunc("PUT /pool/{pool}/bucket", func(w http.ResponseWriter, r *http.Request) {})

	z.router.HandleFunc("DELETE /pool/{pool}/bucket/{bucket}", func(w http.ResponseWriter, r *http.Request) {})

	// Make a secret.
	z.router.HandleFunc("POST /pool/{pool}/secret", func(w http.ResponseWriter, r *http.Request) {})

	z.router.HandleFunc("DELETE /pool/{pool}/secret/{key}", func(w http.ResponseWriter, r *http.Request) {})

	log.Println("Api start service")
	var err1 = z.server.ListenAndServe()
	logger.infof("Api ListenAndServe() done err=%v", err1)
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
	//	user_id = _api.map_claim_to_uid(x_remote_user)
	//	client = request.headers.get("X-REAL-IP")
	//	access_synopsis = [client, user_id, request.method, request.url]
	//	now = int(time.time())
	//	if peer_addr not in _api.trusted_proxies {
	//		logger.error(f"Untrusted proxy: proxy={peer_addr};"
	//			f" Check trusted_proxies in configuration")
	//		body = {"status": "error",
	//			"reason": f"Configuration error (call administrator)",
	//			"time": str(now)}
	//		code = status.HTTP_403_FORBIDDEN
	//		log_access(f"{code}", *access_synopsis)
	//		time.sleep(_api._bad_response_delay)
	//		response = JSONResponse(status_code=code, content=body)
	//		return response
	//	}
	//	if not _api.check_user_is_registered(user_id) {
	//		logger.error(f"Access by an unregistered user:"
	//			f" uid={user_id}, x_remote_user={x_remote_user}")
	//		body = {"status": "error",
	//			"reason": f"Unregistered user: user={user_id}",
	//			"time": str(now)}
	//		code = status.HTTP_401_UNAUTHORIZED
	//		log_access(f"{code}", *access_synopsis)
	//		time.sleep(_api._bad_response_delay)
	//		response = JSONResponse(status_code=code, content=body)
	//		return response
	//	}
	//	response = await call_next(request)
	//	return response
	//    except Exception as e {
	//        m = rephrase_exception_message(e)
	//        logger.error(f"Api GOT AN UNHANDLED EXCEPTION: ({m})",
	//			exc_info=True)
	//        time.sleep(_api._bad_response_delay)
	//        response = _make_status_500_response(m)
	//        return response
	//	}
	agent.ServeHTTP(w, r)
}

// GRANT_ACCESS checks an access to a pool is granted.  It does not
// check the pool-state on deleting a pool.
func grant_access(z *registrar, uid string, pool string, check_pool_state bool) bool {
	/*
		var tables = z.table
		if ensure_mux_is_running(z.table) {
			return false
		}
		if ensure_user_is_authorized(z.table, uid) {
			return false
		}
		if pool != "" {
			if ensure_pool_owner(z.table, pool, uid) {
				return false
			}
		}
		if pool != nil && check_pool_state {
			if ensure_pool_state(z.table, pool, true) {
				return false
			}
		}
	*/
	return true
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

// LIST_POOLS_OF_USER lists pools owned by a user.  It checks the owner
// of a pool if pooi is given.
func list_pools_of_user(z *registrar, uid string, pool string) []*pool_desc_ui {
	var namelist = list_pools(z.table, pool)
	var pools []*pool_desc_ui
	for _, name := range namelist {
		var d = gather_pool_desc(z.table, name)
		if d != nil && d.Owner_uid == uid {
			pools = append(pools, copy_pool_desc_to_ui(d))
		}
	}
	slices.SortFunc(pools, func(x, y *pool_desc_ui) int {
		return strings.Compare(x.Buckets_directory, y.Buckets_directory)
	})
	return pools
}

func map_claim_to_uid(z *registrar, x_remote_user string) string {
	return x_remote_user
}

func copy_pool_desc_to_ui(d *pool_desc) *pool_desc_ui {
	var u = pool_desc_ui{
		// POOL_RECORD
		Pool:              d.Pool,
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

func copy_bucket_desc_to_ui(m map[string]*bucket_record) []*bucket_desc_ui {
	var buckets []*bucket_desc_ui
	for n, d := range m {
		assert_fatal(d.bucket == n)
		var u = &bucket_desc_ui{
			Name:              d.bucket,
			Pool:              d.Pool,
			Bkt_policy:        d.Bkt_policy,
			Modification_time: d.Modification_time,
		}
		buckets = append(buckets, u)
	}
	return buckets
}

func copy_secret_desc_to_ui(m map[string]*secret_record) []*secret_desc_ui {
	var secrets []*secret_desc_ui
	for n, d := range m {
		assert_fatal(d.access_key == n)
		var u = &secret_desc_ui{
			Access_key:        d.access_key,
			Secret_key:        d.Secret_key,
			Pool:              d.Pool,
			Key_policy:        d.Key_policy,
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

func make_new_pool(z *registrar, w http.ResponseWriter, r *http.Request) *pool_desc_response {
	var uid = "AHO"
	var makepool make_pool_request
	var ok1 = decode_request_body(z, r, &makepool)
	if !ok1 {
		http.Error(w, "BAD", http_status_401_unauthorized)
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
		access_key:        "",
		Secret_key:        "",
		Key_policy:        key_policy_READWRITE,
		Expiration_time:   expiration,
		Modification_time: now,
	}
	var probe = set_with_unique_access_key(z.table, secret)
	var ok, oldholder = set_ex_buckets_directory(z.table, makepool.Buckets_directory, pool)
	if !ok {
		delete_pool_name_unconditionally(z.table, pool)
		delete_secret_key_unconditionally(z.table, probe)
		var owner = get_pool_owner_for_messages(z, oldholder)
		raise(reg_error(400, fmt.Sprintf("Buckets-directory is already used:"+
			" path=(%s), holder=(%s)",
			makepool.Buckets_directory, owner)))
		return nil
	}
	set_pool_state(z.table, pool, pool_state_INITIAL, pool_reason_NORMAL)
	// Return a pool info.
	var d = gather_pool_desc(z.table, pool)
	assert_fatal(d != nil)
	var pooldesc2 = copy_pool_desc_to_ui(d)
	return &pool_desc_response{
		Pool_desc: pooldesc2,
	}
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

func get_pool_owner_for_messages(z *registrar, oldholder string) string {
	return "AHO"
}

//(rtoken, stoken) = csrf_protect.generate_csrf_tokens()
//csrf_protect.set_csrf_cookie(stoken, response)
