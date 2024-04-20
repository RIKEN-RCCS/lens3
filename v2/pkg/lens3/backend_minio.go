/* S3-server handler for MinIO. */

// Copyright 2022-2024 RIKEN R-CCS
// SPDX-License-Identifier: BSD-2-Clause

package lens3

import (
	"bytes"
	"encoding/json"
	"context"
	"fmt"
	"syscall"
	"os/exec"
	"log"
	"time"
	"strings"
	//"reflect"
)

type backend_minio struct { }

// wait_line_on_stdout waits until at-least one line is on stdout.  It
// collects stdout/stderr in (outs, errs) as a pair of byte-strings.
// It can return more than one line.  It returns a 4-tuple
// (outs,err,closed,timeout).
func wait_line_on_stdout(cmd *backend_s3, outs string, errs string, timelimit int64) {
    (closed, timeout) = (False, False)
	cmd.Stdout
	cmd.Stderr
    ss = [p.stdout, p.stderr]
    while len(ss) > 0 {
        if limit is None {
            to = None
        } else {
            to = limit - int(time.time())
            if to <= 0 {
                timeout = True
                break
			}
            pass
		}
        (readable, _, _) = select.select(ss, [], [], to)
        if readable == [] {
            timeout = True
            break
		}
        if p.stderr in readable {
            e1 = p.stderr.read1()
            if (e1 == b"") {
                ss = [s for s in ss if s != p.stderr]
                pass
			}
            errs += e1
            pass
		}
        if p.stdout in readable {
            o1 = p.stdout.read1()
            if (o1 == b"") {
                ss = [s for s in ss if s != p.stdout]
                closed = True
                break
			}
            outs += o1
            if b"\n" in o1 {
                break
			}
            pass
		}
        pass
	}
    return (outs, errs, closed, timeout)
}

// wait_to_come_up expects message: "API:, or messages with
// level=FATAL on failure.
//
//         http://xxx.xxx.xxx.xxx:9000 http://xxx.xxx.xxx.xxx:9000
//         http://127.0.0.1:9000".
//
func (*backend_s3) wait_to_come_up(cmd) (bool, bool) {
	//pool_id = self._pool_id
	//tables = self._tables
	//limit = int(time.time()) + self._minio_start_timeout
	//(code, message) = (0, "")
	var o1, e1 string
	var closed, timeout bool
	for {
		(o1, e1, closed, timeout) = wait_line_on_stdout(p, o1, e1, limit)
		(code, message) = _diagnose_minio_message(str(o1, "latin-1"))
		if code != errno.EAGAIN or closed or timeout {
			break
		}
	}
	outs1 = str(o1, "latin-1").strip()
	errs1 = str(e1, "latin-1").strip()
	p_status1 = p.poll()
	if code == 0 {
		logger.info(f"Manager (pool={pool_id}) MinIO outputs message:"
			f" outs=({outs1}) errs=({errs1})")
		return (True, True)
	} else if code == errno.EAGAIN {
		// IT IS NOT AN EXPECTED STATE NOR AN ERROR.  BUT, LET IT
		// CONTINUE THE WORK IF THE PROCESS IS RUNNING.
		if p_status1 is not None {
			logger.error(f"Manager (pool={pool_id}) Starting MinIO failed:"
				f" exit={p_status1} outs=({outs1}) errs=({errs1})")
			set_pool_state(tables, pool_id, Pool_State.INOPERABLE, message)
			return (False, False)
		}else{
			logger.error(f"Manager (pool={pool_id}) starting MinIO"
				f" gets in a dubious state (work continues):"
				f" exit={p_status1} outs=({outs1}) errs=({errs1})")
			return (True, True)
		}
	} else {
		// Terminate the process after extra time to collect messages.
		try {
			(o_, e_) = p.communicate(timeout=1)
			o1 += o_
			e1 += e_
		} except TimeoutExpired {
			pass
		}
		outs2 = str(o1, "latin-1").strip()
		errs2 = str(e1, "latin-1").strip()
		p_status2 = p.poll()
		if code == errno.EADDRINUSE {
			logger.debug(f"Manager (pool={pool_id}) Starting MinIO failed:"
				f" port-in-use (transient);"
				f" exit={p_status2}"
				f" outs=({outs2}) errs=({errs2})")
			return (False, True)
		} else {
			logger.error(f"Manager (pool={pool_id}) Starting MinIO failed:"
				f" exit={p_status2}"
				f" outs=({outs2}) errs=({errs2})")
			set_pool_state(tables, pool_id, Pool_State.INOPERABLE, message)
			return (False, False)
		}
	}
}

// Messages from MinIO at its start-up.

var minio_expected_response = "API:"
// var minio_expected_response = "S3-API:"
var minio_error_response = "ERROR"
var minio_response_port_in_use = "Specified port is already in use"
var minio_response_nonwritable_storage = "Unable to write to the backend"
var minio_response_failure = "Unable to initialize backend"
var minio_response_port_capability = "Insufficient permissions to use specified port"
// var minio_response_X1 = "mkdir /XXX/.minio.sys: permission denied"

type minio_message struct {
	level string
	message string
}

func find_one(mm []interface{}, f func(interface{}) bool) (map[string]interface{}, bool) {
	for i, x = range(mm) {
		var m, ok = x.(map[string]interface{})
		if ok {
			if f(m) {
				return m, true
			}
		}
	}
	return nil, false
}

func has_level_fatal(m map[string]interface{}) bool {
	return (m["level"] == "FATAL")
}

func has_expected_response(m map[string]interface{}) bool {
	var s, ok = m["message"]
	if (ok) {
		return strings.HasPrefix(s, minio_expected_response)
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

// diagnose_minio_message diagnoses messages returned at a MinIO
// start.  It returns 0 on a successful run, EAGAIN on lacking
// expected messages, EADDRINUSE on port-in-use, (EACCES for
// non-writable storage), or EIO or ENOENT on unknown errors.  It
// judges level=FATAL only as an error, but not level=ERROR.
//
func diagnose_minio_message(s []byte)  (syscall.Errno, string) {
	var ss = bytes.Split(s, []byte("\n"))
	var mm []interface{}
	for _, bx := range len(ss) {
		var data interface{}
		var err2 = json.Unmarshal(bx, data)
		if err2 != nil {
			panic(fmt.Sprint("Bad json data from MinIO", err2))
		}
		mm = append(mm, data)
	}
    if len(mm) == 0 {
        return errno.EAGAIN, "MinIO output is empty"
	} else if m1, ok1 := find_one(mm, has_level_fatal); ok1 {
        // Judge the result using the first FATAL message.
		msg1 = get_string(m1, "message")
        if msg1.Contains(minio_response_port_in_use) {
            return (errno.EADDRINUSE, msg1)
		} else if msg1.find(minio_response_nonwritable_storage) != -1 {
            // This case won't happen (2023-06-14).
            return (errno.EACCES, ("MinIO error: " + msg1))
        } else {
            return (errno.EIO, ("MinIO error: " + msg1))
		}
	} else {
		var m2, ok2 = find_one(mm, has_expected_response)
        if ok2 {
			msg2 = get_string(m2, "message")
            return (0, msg2)
        } else {
            return (errno.EAGAIN, "MinIO output contains no expected message")
		}
	}
}
