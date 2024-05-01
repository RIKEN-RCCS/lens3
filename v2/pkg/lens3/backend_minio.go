/* S3-server handler for MinIO. */

// Copyright 2022-2024 RIKEN R-CCS
// SPDX-License-Identifier: BSD-2-Clause

package lens3

import (
	//"bytes"
	//"encoding/json"
	//"context"
	"fmt"
	//"syscall"
	//"os/exec"
	//"log"
	"strings"
	//"time"
	//"reflect"
)

type backend_minio struct {
	backend_process
}

func (svr *backend_minio) get_super_part() *backend_process {
	return &(svr.backend_process)
}

type keyval = map[string]interface{}

// Messages from MinIO at its start-up.
var (
	minio_expected_response = "API:"
	//minio_expected_response_X = "S3-API:"
	minio_error_response               = "ERROR"
	minio_response_port_in_use         = "Specified port is already in use"
	minio_response_nonwritable_storage = "Unable to write to the backend"
	minio_response_failure             = "Unable to initialize backend"
	minio_response_port_capability     = "Insufficient permissions to use specified port"
	//minio_response_X1 = "mkdir /XXX/.minio.sys: permission denied"
)

type minio_message struct {
	level   string
	errKind string
	time    string
	message string
	//"error": {"message":, "source":}
}

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

func check_fatal_exists(mm []map[string]interface{}) (map[string]interface{}, bool) {
	return find_one(mm, has_level_fatal)
}

// Note It works with a missing key, because fetching a missing key
// from a map returns a zero-value.
func has_level_fatal(m map[string]interface{}) bool {
	return (m["level"] == "FATAL")
}

func check_expected_exists(mm []map[string]interface{}) (map[string]interface{}, bool) {
	return find_one(mm, has_expected_response)
}

func has_expected_response(m map[string]interface{}) bool {
	var s = get_string(m, "message")
	return strings.HasPrefix(s, minio_expected_response)
}

// GET_STRING returns a string field at the key in the map m.  It
// returns "", if a field is missing or non-string.
func get_string(m map[string]interface{}, key string) string {
	var m1, ok1 = m[key]
	if !ok1 {
		// assert_fatal(ok1)
		return ""
	}
	var m2, ok2 = m1.(string)
	if !ok2 {
		// assert_fatal(ok2)
		return ""
	}
	return m2
}

func (svr *backend_minio) check_startup(outerr int, ss []string) start_result {
	fmt.Println("minio.check_startup()")
	var mm = decode_json(ss)
	//fmt.Printf("mm=%T\n", mm)
	if len(mm) == 0 {
		return start_result{
			start_state: start_ongoing,
			message:     "OK",
		}
	}
	var m1, fatal1 = check_fatal_exists(mm)
	if fatal1 {
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
	var m2, expected1 = check_expected_exists(mm)
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
		message:     "OK",
	}
}

func (svr *backend_minio) shutdown() {
	fmt.Println("minio.shutdown()")
}
