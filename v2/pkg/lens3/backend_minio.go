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

func (svr *backend_minio) get_generic_part() *backend_process {
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

func check_no_fatal(mm []map[string]interface{}) bool {
	var _, any = find_one(mm, has_level_fatal)
	return any
}

func has_level_fatal(m map[string]interface{}) bool {
	return (m["level"] == "FATAL")
}

func has_expected_response(m map[string]interface{}) bool {
	var s1, ok = m["message"]
	if ok {
		switch s := s1.(type) {
		case string:
			return strings.HasPrefix(s, minio_expected_response)
		default:
			panic("backend bad message")
		}
	} else {
		return false
	}
}

// get_string returns a string field at the key k in the map m.  A
// field missing or a non-string invokes a panic.
func get_string(m map[string]interface{}, k string) string {
	var m1, ok1 = m["message"]
	assert_fatal(ok1)
	var m2, ok2 = m1.(string)
	assert_fatal(ok2)
	return m2
}

func (svr *backend_minio) check_startup(int, []string) start_result {
	fmt.Println("minio.check_startup()")
	return start_result{
		start_state: start_ongoing,
		message:     "OK",
	}
}

func (svr *backend_minio) shutdown() {
	fmt.Println("minio.shutdown()")
}
