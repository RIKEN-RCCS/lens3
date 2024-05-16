/* Lens3-Api.  It is a pool mangement. */

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
	"strconv"
	"strings"
	//"time"
	//"runtime"
)

import "embed"

//go:embed ui
var efs embed.FS

//{policy: "readwrite", keys: pool_data.secrets_rw},
//{policy: "readonly", keys: pool_data.secrets_ro},
//{policy: "writeonly", keys: pool_data.secrets_wo},

type registrar struct {
	table *keyval_table

	server *http.Server
	router *http.ServeMux

	lens3_version string

	*api_conf
	//registrar_conf
}

type response_to_ui interface{ response_union() }

func (*pool_desc_response) response_union() {}
func (*user_info_response) response_union() {}

type response_to_ui_common struct {
	// Status is "success" or "error".
	Status       string `json:"status"`
	Reason       string `json:"reason"`
	X_csrf_token string `json:"x_csrf_token"`
	Time         string `json:"time"`
}

// RESPONSE_TO_UI is the json format of the response to UI.  See also
// the function set_pool_data() in "v1/ui/src/lens3c.ts".
type pool_desc_response struct {
	response_to_ui_common
	Pool_desc pool_desc_ui `json:"pool_desc"`
}

// POOL_DESC_UI is a subfield of response_to_ui.
type pool_desc_ui struct {
	response_to_ui_common
	Pool_name           string           `json:"pool_name"`
	Buckets_directory   string           `json:"buckets_directory"`
	Owner_uid           string           `json:"owner_uid"`
	Owner_gid           string           `json:"owner_gid"`
	Buckets             []bucket_desc_ui `json:"buckets"`
	Secrets             []secret_desc_ui `json:"secrets"`
	Probe_key           string           `json:"probe_key"`
	Expiration_time     int64            `json:"expiration_time"`
	Online_status       string           `json:"online_status"`
	User_enabled_status bool             `json:"user_enabled_status"`
	Minio_state         string           `json:"minio_state"`
	Minio_reason        string           `json:"minio_reason"`
	Modification_time   int64            `json:"modification_time"`
	Time                int64            `json:"time"`
}

type bucket_desc_ui struct {
	Name              string `json:"name"`
	Pool              string `json:"pool"`
	Bkt_policy        string `json:"bkt_policy"`
	Modification_time int64  `json:"modification_time"`
}

type secret_desc_ui struct {
	Access_key        string `json:"access_key"`
	Secret_key        string `json:"secret_key"`
	Pool              string `json:"owner"`
	Key_policy        string `json:"key_policy"`
	Expiration_time   int64  `json:"expiration_time"`
	Modification_time int64  `json:"modification_time"`
}

type user_info_response struct {
	response_to_ui_common
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

var the_registrar = registrar{}

var err_body_not_allowed = errors.New("http: request method or response status code does not allow body")

func configure_registrar(z *registrar, t *keyval_table, conf *api_conf) {
	z.table = t
	z.api_conf = conf
	z.lens3_version = "v2.1"
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
		return_file(z, w, r, r.URL.Path)
	})

	z.router.HandleFunc("GET /ui2/", func(w http.ResponseWriter, r *http.Request) {
		defer handle_proxy_exc(z, w, r)
		return_file(z, w, r, r.URL.Path)
	})

	// This returns a user information and initializes the CSRF state.
	z.router.HandleFunc("GET /user-info", func(w http.ResponseWriter, r *http.Request) {
		defer handle_proxy_exc(z, w, r)
		var uid = "???"
		//grant_access(z, uid, nil, false)
		var u = get_user(z.table, uid)
		if u == nil {
			u = &User_record{
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
			Lens3_version: z.lens3_version,
			S3_url:        z.UI.S3_url,
			Footer_banner: z.UI.Footer_banner,
		}
		var rspn = &user_info_response{
			//response_to_ui_common: uic,
			response_to_ui_common: response_to_ui_common{
				Status:       "success",
				Reason:       "",
				X_csrf_token: "???",
				Time:         "???",
			},
			User_info: *info,
		}
		var v1, err1 = json.Marshal(rspn)
		if err1 != nil {
			panic(err1)
		}
		fmt.Println("GET(/user-info)=", string(v1))
		io.WriteString(w, string(v1))
	})

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
		fmt.Println("stacktrace from panic: \n" + string(debug.Stack()))
		//http.Error(w, "BAD", http_status_500_internal_server_error)
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

func return_ui_script(z *registrar, w http.ResponseWriter, r *http.Request, path string) {
	defer handle_proxy_exc(z, w, r)
	var data1, err1 = efs.ReadFile(path)
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

func return_file(z *registrar, w http.ResponseWriter, r *http.Request, path string) {
	defer handle_proxy_exc(z, w, r)
	var data1, err1 = efs.ReadFile(path)
	if err1 != nil {
		http.Error(w, "BAD", http_status_500_internal_server_error)
		return
	}
	io.WriteString(w, string(data1))
}

//(rtoken, stoken) = csrf_protect.generate_csrf_tokens()
//csrf_protect.set_csrf_cookie(stoken, response)
