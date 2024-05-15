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
	"path/filepath"
	//"log"
	"net/http"
	"runtime"
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

// BACKEND_MINIO is a manager for MinIO.
type backend_minio struct {
	backend_process

	heartbeat_client *http.Client
	heartbeat_url    string
	failure_message  string

	mc_alias      string
	mc_config_dir string

	//g.env_minio map[string]string
	//g.env_mc map[string]string

	*backend_minio_conf
}

// BACKEND_MINIO_CONF is a static and common part of a manager.  It
// is embedded.  It also doubles as a factory.
type backend_minio_conf struct {
	bin_minio string
	bin_mc    string

	minio_setup_at_start    bool
	minio_start_timeout     time.Duration
	minio_setup_timeout     time.Duration
	minio_stop_timeout      time.Duration
	minio_mc_timeout        time.Duration
	minio_watch_gap_minimal time.Duration
}

type keyval = map[string]interface{}

type minio_message_ struct {
	level   string
	errKind string
	time    string
	message string
	//"error": {"message":, "source":}
}

var the_backend_minio_factory = &backend_minio_conf{}

func (be *backend_minio_conf) make_backend(pool string) backend {
	var g = &backend_minio{}
	g.Pool = pool
	g.manager_conf = the_manager_conf
	g.backend_minio_conf = the_backend_minio_factory
	runtime.SetFinalizer(g, finalize_backend_minio)
	return g
}

func (be *backend_minio_conf) configure() {
	be.bin_minio = "/usr/local/bin/minio"
	be.bin_mc = "/usr/local/bin/mc"

	be.minio_setup_at_start = true
	be.minio_start_timeout = 60
	be.minio_setup_timeout = 60
	be.minio_stop_timeout = 30
	be.minio_mc_timeout = 60
	//be.minio_watch_gap_minimal = 30
}

func (be *backend_minio_conf) clean_at_exit() {
	clean_tmp()
}

func finalize_backend_minio(g *backend_minio) {
	if g.mc_config_dir != "" {
		os.RemoveAll(g.mc_config_dir)
		g.mc_config_dir = ""
	}
}

func (g *backend_minio) get_super_part() *backend_process {
	return &(g.backend_process)
}

func (proc *backend_minio) make_command_line(address string, directory string) backend_command {
	var argv = []string{
		proc.bin_minio,
		"--json", "--anonymous", "server",
		"--address", address, directory}
	var envs = []string{
		fmt.Sprintf("MINIO_ROOT_USER=%s", proc.Root_access),
		fmt.Sprintf("MINIO_ROOT_PASSWORD=%s", proc.Root_secret),
		fmt.Sprintf("MINIO_BROWSER=%s", "off"),
	}
	return backend_command{argv, envs}
}

// CHECK_STARTUP decides the server state.  It looks for an expected
// response, when no messages are "level=FATAL".  Otherwise, in case
// of an error with messages "level=FATAL", it diagnoses the cause of
// the error by the first fatal message.  It returns a retry response
// only on the port-in-use error.
func (g *backend_minio) check_startup(outerr int, ss []string) start_result {
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

func (g *backend_minio) establish() {
	fmt.Println("minio.establish()")
	var _ = mc_alias_set(g)
}

// SHUTDOWN stops a server.  It first tries MC admin-service-stop,
// then tries ...
func (g *backend_minio) shutdown() error {
	fmt.Println("minio.shutdown()")
	var proc = g.get_super_part()

	logger.debugf("Mux(pool=%s) stopping MinIO: %v.",
		proc.Pool, proc)
	//assert_fatal(g.mc_alias != nil)
	//defer mc_alias_remove(svr)
	var v1 = mc_admin_service_stop(g)
	if v1.values != nil {
	}
	return nil
}

// HEARTBEAT http-gets the path "/minio/health/live" and returns an
// http status code.  It returns 500 on a connection failure.
func (g *backend_minio) heartbeat() int {
	//fmt.Println("minio.heartbeat()")
	var proc = g.get_super_part()

	if g.heartbeat_client == nil {
		//fmt.Println("minio.heartbeat(1) proc=", proc)
		var timeout = (time.Duration(proc.Heartbeat_timeout) * time.Second)
		//fmt.Println("minio.heartbeat(2) proc=", proc)
		g.heartbeat_client = &http.Client{
			Timeout: timeout,
		}
		g.heartbeat_url = fmt.Sprintf("http://%s/minio/health/live", proc.Backend_ep)
		g.failure_message = fmt.Sprintf("Mux(pool=%s)"+
			" Heartbeating MinIO failed: urlopen error,"+
			" url=(%s);", proc.Pool, g.heartbeat_url)
	}

	var c = g.heartbeat_client
	var rsp, err1 = c.Get(g.heartbeat_url)
	if err1 != nil {
		logger.debugf("Mux(pool=%s) Heartbeat MinIO failed: %s.\n",
			proc.Pool, err1)
		return 500
	}
	defer rsp.Body.Close()
	var _, err2 = io.ReadAll(rsp.Body)
	if err2 != nil {
		panic(err2)
	}
	//fmt.Println("heartbeat code=", rsp.StatusCode)
	//fmt.Println("heartbeat msg=", m)
	if proc.verbose {
		logger.debugf("Mux(pool=%s) Heartbeat MinIO: count=%d code=%d.",
			proc.Pool, proc.heartbeat_misses, rsp.StatusCode)
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

func clean_tmp() {
	var d = os.TempDir()
	var pattern = fmt.Sprintf("%s/lens3-mc-*", d)
	var matches, err1 = filepath.Glob(pattern)
	assert_fatal(err1 != nil)
	// (err1 == nil || err1 == filepath.ErrBadPattern)
	for _, p := range matches {
		logger.debugf("Mux() Clean by os.RemoveAll(%s).", p)
		var err2 = os.RemoveAll(p)
		if err2 != nil {
			// (err2 : *os.PathError)
			fmt.Print("os.RemoveAll=", err2)
		}
	}
}

// *** MC-COMMANDS ***

// MC_RESULT is a decoding of an output of a MC-command.  On an error, a
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
		logger.error("Mux() json-decode failed")
		var msg1 = fmt.Sprintf("MC-command returned a bad json: (%s)", s)
		return mc_result{nil, msg1}
	}

	for _, m := range mm {
		switch get_string(m, "status") {
		case "success":
			// Skip.
		case "error":
			if len(mm) != 1 {
				logger.warnf("Mux() MC-command with multiple errors: (%v)", mm)
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

// EXECUTE_MC_CMD runs an MC-command command and checks its output.
// Note that a timeout kills the process by SIGKILL.  MEMO: Timeout of
// context returns "context.deadlineExceededError".
func execute_mc_cmd(g *backend_minio, name string, command []string) mc_result {
	//var proc = g.get_super_part()
	assert_fatal(g.mc_alias != "" && g.mc_config_dir != "")
	var argv = append([]string{
		g.bin_mc,
		"--json",
		fmt.Sprintf("--config-dir=%s", g.mc_config_dir)},
		command...)
	var timeout = (g.minio_mc_timeout * time.Second)
	var ctx, cancel = context.WithTimeout(context.Background(), timeout)
	defer cancel()
	var cmd = exec.CommandContext(ctx, argv[0], argv[1:]...)
	var outb, errb bytes.Buffer
	cmd.Stdin = nil
	cmd.Stdout = &outb
	cmd.Stderr = &errb
	cmd.Env = *g.environ
	var err1 = cmd.Run()
	fmt.Println("cmd.Run()=", err1)
	switch err := err1.(type) {
	case nil:
		// OK.
	case *exec.ExitError:
		// Not successful.
		var status = err.ProcessState.ExitCode()
		logger.errorf(("Mux(pool=) MC-command failed:" +
			" cmd=%v; exit=%d error=(%v) stdout=(%s) stderr=(%s)"),
			argv, status, err, outb.String(), errb.String())
	default:
		fmt.Printf("cmd.Run()=%T %v", err1, err1)
		logger.errorf(("Mux(pool=) MC-command failed:" +
			" cmd=%v; error=(%v) stdout=(%s) stderr=(%s)"),
			argv, err, outb.String(), errb.String())
	}
	var wstatus = cmd.ProcessState.ExitCode()
	if g.verbose {
		logger.debugf(("Mux(pool=) MC-command done:" +
			" cmd=%v; status=%v stdout=(%s) stderr=(%s)"),
			argv, wstatus, outb.String(), errb.String())
	}
	if wstatus == -1 {
		logger.errorf(("Mux(pool=) MC-command unfinished:" +
			" cmd=%v; stdout=(%s) stderr=(%s)"),
			argv, outb.String(), errb.String())
		var msg2 = fmt.Sprintf("MC-command unfinished: (%s)", outb.String())
		return mc_result{nil, msg2}
	}
	var v1 = simplify_mc_message(outb.Bytes())
	if v1.values != nil {
		if g.verbose {
			logger.debugf("Mux(pool=) MC-command OK: cmd=%v", command)
		} else {
			logger.debugf("Mux(pool=) MC-command OK: cmd=%s", name)
		}
	} else {
		logger.errorf(("Mux(pool=) MC-command failed:" +
			" cmd=%v; error=%v stdout=(%v) stderr=(%v)"),
			argv, v1.cause, outb, errb)
	}
	return v1
}

func mc_alias_set(g *backend_minio) mc_result {
	assert_fatal(g.mc_alias == "" && g.mc_config_dir == "")
	var rnd = strings.ToLower(random_string(12))
	var url = fmt.Sprintf("http://%s", g.Backend_ep)
	//g.mc_config_dir = tempfile.TemporaryDirectory()
	var dir, err1 = os.MkdirTemp("", "lens3-mc-")
	if err1 != nil {
		logger.errorf("Mux(pool=) %s", err1)
		return mc_result{nil, err1.Error()}
	}
	g.mc_config_dir = dir
	g.mc_alias = fmt.Sprintf("pool-%s-%s", g.Pool, rnd)
	var v1 = execute_mc_cmd(g, "alias_set",
		[]string{"alias", "set", g.mc_alias, url,
			g.Root_access, g.Root_secret,
			"--api", "S3v4"})
	if v1.values == nil {
		g.mc_alias = ""
		g.mc_config_dir = ""
	}
	return v1
}

func mc_alias_remove(g *backend_minio) mc_result {
	assert_fatal(g.mc_alias != "" && g.mc_config_dir != "")
	var v1 = execute_mc_cmd(g, "alias_remove",
		[]string{"alias", "remove", g.mc_alias})
	if v1.values == nil {
		g.mc_alias = ""
		g.mc_config_dir = ""
	}
	return v1
}

func mc_admin_service_stop(g *backend_minio) mc_result {
	var v1 = execute_mc_cmd(g, "admin_service_stop",
		[]string{"admin", "service", "stop", g.mc_alias})
	return v1
}
