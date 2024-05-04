/* S3-server handler for MinIO. */

// Copyright 2022-2024 RIKEN R-CCS
// SPDX-License-Identifier: BSD-2-Clause

package lens3

import (
	"bytes"
	//"encoding/json"
	"context"
	"fmt"
	"io"
	//"maps"
	"time"
	//"syscall"
	"os"
	"os/exec"
	//"log"
	"net/http"
	"strings"
	//"time"
	//"reflect"
)

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

// BACKEND_MINIO_TEMPLATE is a dummy manager to make a command line
// arguments.
type backend_minio_template struct {
	backend_minio_common
}

// BACKEND_MINIO is a manager for MinIO.
type backend_minio struct {
	backend_process
	backend_minio_common

	heartbeat_client *http.Client
	heartbeat_url    string
	failure_message  string

	mc_alias      string
	mc_config_dir string

	//svr.env_minio map[string]string
	//svr.env_mc map[string]string
}

// BACKEND_MINIO_COMMON is a static and common part of a manager.  It
// is embedded.
type backend_minio_common struct {
	mc_command string

	minio_environ []string

	minio_mc_timeout        int
	minio_awake_duration    int
	minio_setup_at_start    bool
	minio_setup_timeout     int
	minio_start_timeout     int
	minio_stop_timeout      int
	minio_watch_gap_minimal int
}

type keyval = map[string]interface{}

type minio_message_ struct {
	level   string
	errKind string
	time    string
	message string
	//"error": {"message":, "source":}
}

func (be *backend_minio_template) make_backend(string, string) backend {
	return &backend_minio{}
}

func (svr *backend_minio) get_super_part() *backend_process {
	return &(svr.backend_process)
}

func (svr *backend_minio) make_command_line(address string, directory string) backend_command {
	var bin_minio = "/usr/local/bin/minio"
	var argv = []string{
		bin_minio,
		"--json", "--anonymous", "server",
		"--address", address, directory}
	//svr.env_minio["MINIO_ROOT_USER"] = svr.minio_root_user
	//svr.env_minio["MINIO_ROOT_PASSWORD"] = svr.minio_root_password
	//svr.env_minio["MINIO_BROWSER"] = "off"
	var envs = []string{
		fmt.Sprintf("MINIO_ROOT_USER=%s", svr.root_user),
		fmt.Sprintf("MINIO_ROOT_PASSWORD=%s", svr.root_password),
		fmt.Sprintf("MINIO_BROWSER=%s", "off"),
	}
	return backend_command{argv, envs}
}

func (svr *backend_minio) setup() {
	svr.root_user = generate_access_key()
	svr.root_password = generate_secret_key()
	svr.minio_environ = minimal_environ()
	//svr.env_minio["MINIO_ROOT_USER"] = svr.minio_root_user
	//svr.env_minio["MINIO_ROOT_PASSWORD"] = svr.minio_root_password
	//svr.env_minio["MINIO_BROWSER"] = "off"
}

// CHECK_STARTUP decides the server state.  It looks for an expected
// response, when no messages are "level=FATAL".  Otherwise, in case
// of an error with messages "level=FATAL", it diagnoses the cause of
// the error from the first fatal message.  It returns a retry
// response only on the port-in-use error.
func (svr *backend_minio) check_startup(outerr int, ss []string) start_result {
	fmt.Println("minio.check_startup()")
	var mm, _ = decode_json(ss)
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

// SHUTDOWN stops a server.  It first tries MC admin-service-stop,
// then tries ...
func (svr *backend_minio) shutdown() error {
	fmt.Println("minio.shutdown()")
	var proc = svr.get_super_part()

	logger.debugf("Mux(pool=%s) stopping MinIO: %v.",
		proc.pool, proc)
	//assert_fatal(svr.mc_alias != nil)
	defer mc_alias_remove(svr)
	var v1 = mc_admin_service_stop(svr)
	if v1.values != nil {
	}
	return nil
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
		svr.failure_message = fmt.Sprintf("Mux(pool=%s)"+
			" Heartbeating MinIO failed: urlopen error,"+
			" url=(%s);", proc.pool, svr.heartbeat_url)
	}

	var c = svr.heartbeat_client
	var rsp, err1 = c.Get(svr.heartbeat_url)
	if err1 != nil {
		logger.debug(fmt.Sprintf("Heartbeat MinIO failed (pool=%s): %s.\n",
			proc.pool, err1))
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
		logger.debugf("Mux(pool=%s) Heartbeat MinIO.", proc.pool)
	}
	return rsp.StatusCode
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

// *** MC-COMMANDS ***

// MC_RESULT is a decoding of an output of MC-command.  On an error, a
// values field is nil and a cause code is set.
type mc_result struct {
	values []map[string]any
	cause  string
}

// SIMPLIFY_MC_MESSAGE returns a 2-tuple {[value,...], ""} on success,
// or {nil, error-cause} on failure.  It extracts a message part from
// an error message.  MC-command may return zero or more values as
// separate json records.  An empty output is a proper success.  Each
// record is {"status": "success", ...}, containing a value.  An error
// record looks like: {"status": "error", "error": {"message":, ...,
// "cause": {"error": {"Code": ..., ...}}}}.  The
// "error/cause/error/Code" slot will be a keyword of useful
// information if it exists.  A returned 2-tuple may have a whole
// message instead of a cause-code if the slot is missing.
func simplify_mc_message(s []byte) mc_result {
	var mm, ok = decode_json([]string{string(s)})
	if !ok {
		logger.error("json-decode failed")
		var msg1 = fmt.Sprintf("MC-command returned a bad json: (%s)", s)
		return mc_result{nil, msg1}
	}

	for _, m := range mm {
		switch get_string(m, "status") {
		case "success":
			// Skip.
		case "error":
			if len(mm) != 1 {
				logger.warnf("MC-command with multiple errors: (%v)", mm)
			}
			var m1 = get_string(m, "error", "cause", "error", "Code")
			if m1 != "" {
				return mc_result{nil, m1}
			}
			var m2 = get_string(m, "error", "message")
			if m2 != "" {
				return mc_result{nil, m2}
			}
			return mc_result{nil, fmt.Sprintf("%s", m)}
		default:
			// Unknown status.
			return mc_result{nil, fmt.Sprintf("%s", m)}
		}
	}
	return mc_result{mm, ""}
}

// EXECUTE_MC_CMD runs a command and checks its output.  Note that a
// timeout kills the process by SIGKILL.
func execute_mc_cmd(svr *backend_minio, name string, command []string) mc_result {
	assert_fatal(svr.mc_alias != "" && svr.mc_config_dir != "")
	var args = append([]string{
		"--json",
		fmt.Sprintf("--config-dir=%s", svr.mc_config_dir)},
		command...)
	var timeout = time.Duration(svr.minio_mc_timeout) * time.Second
	var ctx, cancel = context.WithTimeout(context.Background(), timeout)
	defer cancel()
	var cmd = exec.CommandContext(ctx, svr.mc_command, args...)
	var outb, errb bytes.Buffer
	cmd.Stdin = nil
	cmd.Stdout = &outb
	cmd.Stderr = &errb
	cmd.Env = svr.minio_environ
	var err1 = cmd.Run()
	switch err := err1.(type) {
	case nil:
	case *exec.ExitError:
		if err.ProcessState.ExitCode() == -1 {
			logger.error("MC-command killed (timeout)")
		}
		logger.errorf(("MC-command failed:" +
			" cmd=%v; error=%v stdout=(%s) stderr=(%s)"),
			command, err, outb.String(), errb.String())
	default:
		logger.errorf(("MC-command failed:" +
			" cmd=%v; error=%v stdout=(%s) stderr=(%s)"),
			command, err, outb.String(), errb.String())
	}
	var wstatus = cmd.ProcessState.ExitCode()
	if svr.verbose {
		logger.debugf(("MC-command done:" +
			" cmd=%v; status=%v stdout=(%s) stderr=(%s)"),
			command, wstatus, outb.String(), errb.String())
	}
	if wstatus == -1 {
		logger.errorf(("MC-command unfinished:" +
			" cmd=%v; stdout=(%s) stderr=(%s)"),
			command, outb.String(), errb.String())
		var msg2 = fmt.Sprintf("MC-command unfinished: (%s)", outb.String())
		return mc_result{nil, msg2}
	}
	var v1 = simplify_mc_message(outb.Bytes())
	if v1.values != nil {
		if svr.verbose {
			logger.debugf("MC-command OK: cmd=%v", command)
		} else {
			logger.debugf("MC-command OK: cmd=%s", name)
		}
	} else {
		logger.errorf(("MC-command failed:" +
			" cmd=%v; error=%v stdout=(%v) stderr=(%v)"),
			command, v1.cause, outb, errb)
	}
	return v1
}

func mc_alias_set(svr *backend_minio) {
	assert_fatal(svr.mc_alias == "" && svr.mc_config_dir == "")
	var rnd = strings.ToLower(random_string(12))
	var url = fmt.Sprintf("http://%s", svr.ep)
	//svr.mc_config_dir = tempfile.TemporaryDirectory()
	var dir, err1 = os.MkdirTemp("", "lens3-mc")
	if err1 != nil {
		logger.errorf("%s", err1)
		return
	}
	svr.mc_config_dir = dir
	svr.mc_alias = fmt.Sprintf("%s-%s", svr.pool, rnd)
	var v1 = execute_mc_cmd(svr, "alias_set",
		[]string{"alias", "set", svr.mc_alias, url,
			svr.root_user, svr.root_password,
			"--api", "S3v4"})
	if v1.values == nil {
		svr.mc_alias = ""
		svr.mc_config_dir = ""
	}
}

func mc_alias_remove(svr *backend_minio) {
	var v1 = execute_mc_cmd(svr, "alias_remove",
		[]string{"alias", "remove", svr.mc_alias})
	if v1.values == nil {
	}
	svr.mc_alias = ""
	svr.mc_config_dir = ""
}

func mc_admin_service_stop(svr *backend_minio) mc_result {
	var v1 = execute_mc_cmd(svr, "admin_service_stop",
		[]string{"admin", "service", "stop", svr.mc_alias})
	return v1
}
