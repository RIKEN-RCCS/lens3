/* S3-server handler for MinIO. */

// Copyright 2022-2024 RIKEN R-CCS
// SPDX-License-Identifier: BSD-2-Clause

package lens3

import (
	//"bytes"
	//"encoding/json"
	//"context"
	"fmt"
	"io"
	"time"
	//"syscall"
	//"os/exec"
	//"log"
	"net/http"
	"strings"
	//"time"
	//"reflect"
)

type backend_minio struct {
	backend_generic

	heartbeat_client *http.Client
	heartbeat_url    string
	failure_message  string
}

func (svr *backend_minio) get_super_part() *backend_generic {
	return &(svr.backend_generic)
}

type keyval = map[string]interface{}

// Message prefixes from MinIO at its start-up.
var (
	minio_expected_response    = "API:"
	minio_response_port_in_use = "Specified port is already in use"
	// minio_response_port_capability = "Insufficient permissions to use specified port"
	// minio_response_bad_endpoint = "empty or root endpoint is not supported"
	// minio_response_nonwritable = "mkdir ...: permission denied"
	// minio_expected_response_X_ = "S3-API:"
	// minio_response_error_ = "ERROR"
	// minio_response_nonwritable_storage_ = "Unable to write to the backend"
	// minio_response_failure_ = "Unable to initialize backend"
)

type minio_message_ struct {
	level   string
	errKind string
	time    string
	message string
	//"error": {"message":, "source":}
}

// FIND_ONE searches in a list for one satisfies f.  It returns a
// boolean and the first satisfying one if it exists.
func find_one(mm []map[string]interface{}, f func(map[string]interface{}) bool) (map[string]interface{}, bool) {
	for _, m := range mm {
		//var m, ok = x.(map[string]interface{})
		//if ok {
		if f(m) {
			return m, true
		}
		//}
	}
	return nil, false
}

// Note It works with a missing key, because fetching a missing key
// from a map returns a zero-value.
func has_level_fatal(m map[string]interface{}) bool {
	return (m["level"] == "FATAL")
}

func has_expected_response(m map[string]interface{}) bool {
	var s = get_string(m, "message")
	return strings.HasPrefix(s, minio_expected_response)
}

// GET_STRING returns a string field at the key in the map.  It
// returns "", if a field is missing or non-string.
func get_string(m map[string]interface{}, key string) string {
	var m1, ok1 = m[key]
	if !ok1 {
		return ""
	}
	var m2, ok2 = m1.(string)
	if !ok2 {
		return ""
	}
	return m2
}

// CHECK_STARTUP determines the server state.  It looks for an
// expected response, when no messages are "level=FATAL".  Otherwise,
// in case of an error with messages "level=FATAL", it decides the
// cause of the error from the first message.  It returns a retry
// response only on port-in-use error.
func (svr *backend_minio) check_startup(outerr int, ss []string) start_result {
	fmt.Println("minio.check_startup()")
	var mm = decode_json(ss)
	//fmt.Printf("mm=%T\n", mm)
	if len(mm) == 0 {
		return start_result{
			start_state: start_ongoing,
			message:     "--",
		}
	}
	// var m1, fatal1 = check_fatal_exists(mm)
	var m1, error1 = find_one(mm, has_level_fatal)
	if error1 {
		assert_fatal(m1 != nil)
		var msg = get_string(m1, "message")
		switch {
		case strings.HasPrefix(msg, minio_response_port_in_use):
			return start_result{
				start_state: start_to_retry,
				message:     msg,
			}
		default:
			return start_result{
				start_state: start_failed,
				message:     msg,
			}
		}
	}
	// var m2, expected1 = check_expected_exists(mm)
	var m2, expected1 = find_one(mm, has_expected_response)
	if expected1 {
		assert_fatal(m2 != nil)
		var msg = get_string(m2, "message")
		fmt.Println("EXPECTED=", msg)
		return start_result{
			start_state: start_started,
			message:     msg,
		}
	}
	return start_result{
		start_state: start_ongoing,
		message:     "--",
	}
}

func (svr *backend_minio) shutdown() {
	fmt.Println("minio.shutdown()")
}

// HEARTBEAT http-gets the path "/minio/health/live" and returns an
// http status code.  It returns 500 on a connection failure.
func (svr *backend_minio) heartbeat() int {
	fmt.Println("minio.heartbeat()")
	var proc = svr.get_super_part()

	if svr.heartbeat_client == nil {
		var timeout = time.Duration(proc.heartbeat_timeout) * time.Second
		svr.heartbeat_client = &http.Client{
			Timeout: timeout,
		}
		svr.heartbeat_url = fmt.Sprintf("http://%s/minio/health/live", proc.ep)
		svr.failure_message = fmt.Sprintf("Manager (pool=%s)"+
			" Heartbeating MinIO failed: urlopen error,"+
			" url=(%s);", proc.pool_id, svr.heartbeat_url)
	}

	var c = svr.heartbeat_client
	var rsp, err1 = c.Get(svr.heartbeat_url)
	if err1 != nil {
		logger.Debug(fmt.Sprintf("Heartbeat MinIO failed (pool=%s): %s.\n",
			proc.pool_id, err1))
		return 500
	}
	defer rsp.Body.Close()
	var _, err2 = io.ReadAll(rsp.Body)
	if err2 != nil {
		panic(err2)
	}
	fmt.Println("heartbeat code=", rsp.StatusCode)
	//fmt.Println("heartbeat msg=", m)
	if proc.verbose {
		logger.Debug("Manager (pool={pool_id}) Heartbeat MinIO.")
	}
	return rsp.StatusCode
}
