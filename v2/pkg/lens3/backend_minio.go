/* S3-server handler for MinIO. */

// Copyright 2022-2024 RIKEN R-CCS
// SPDX-License-Identifier: BSD-2-Clause

package lens3

import (
	"bytes"
	"errors"
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
	//failure_message  string

	mc_alias      string
	mc_config_dir string

	//g.env_minio map[string]string
	//g.env_mc map[string]string

	*backend_minio_conf
}

// BACKEND_MINIO_CONF is a static and common part of a MinIO backend.
// It doubles as a factory.
type backend_minio_conf struct {
	*minio_conf
	//bin_minio string
	//bin_mc    string

	//*manager_conf
	// In manager_conf.
	//minio_setup_at_start    bool
	//minio_start_timeout     time.Duration
	//minio_setup_timeout     time.Duration
	//minio_stop_timeout      time.Duration
	//minio_mc_timeout        time.Duration
	//minio_watch_gap_minimal time.Duration
}

var the_backend_minio_factory = &backend_minio_conf{}

func (fa *backend_minio_conf) make_backend(pool string) backend {
	var g = &backend_minio{}
	// Set the super part.
	g.Pool = pool
	g.be = nil
	g.manager_conf = &the_manager.manager_conf
	// Set the local part.
	g.backend_minio_conf = the_backend_minio_factory
	runtime.SetFinalizer(g, finalize_backend_minio)
	return g
}

func (fa *backend_minio_conf) configure(conf *mux_conf) {
	fa.minio_conf = &conf.Minio

	//fa.bin_minio = "/usr/local/bin/minio"
	//fa.bin_mc = "/usr/local/bin/mc"

	//fa.minio_setup_at_start = true
	//fa.minio_start_timeout = 60
	//fa.minio_setup_timeout = 60
	//fa.minio_stop_timeout = 30
	//fa.minio_mc_timeout = 60
	//fa.minio_watch_gap_minimal = 30
}

func (fa *backend_minio_conf) clean_at_exit() {
	clean_tmp()
}

func finalize_backend_minio(d *backend_minio) {
	if d.mc_config_dir != "" {
		os.RemoveAll(d.mc_config_dir)
		d.mc_config_dir = ""
	}
}

func (d *backend_minio) get_super_part() *backend_process {
	return &(d.backend_process)
}

func (proc *backend_minio) make_command_line(address string, directory string) backend_command {
	var argv = []string{
		proc.Minio,
		"--json", "--anonymous", "server",
		"--address", address, directory}
	var envs = []string{
		fmt.Sprintf("MINIO_ROOT_USER=%s", proc.be.Root_access),
		fmt.Sprintf("MINIO_ROOT_PASSWORD=%s", proc.be.Root_secret),
		fmt.Sprintf("MINIO_BROWSER=%s", "off"),
	}
	return backend_command{argv, envs}
}

// CHECK_STARTUP decides the server state.  It looks for an expected
// response, when no messages are "level=FATAL".  Otherwise, in case
// of an error with messages "level=FATAL", it diagnoses the cause of
// the error by the first fatal message.  It returns a retry response
// only on the port-in-use error.
func (d *backend_minio) check_startup(outerr int, ss []string) start_result {
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
		fmt.Println("*** EXPECTED=", msg)
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

func (d *backend_minio) establish() error {
	fmt.Println("minio.establish()")
	var v1 = minio_mc_alias_set(d)
	return v1.err
}

// SHUTDOWN stops a server using MC admin-service-stop.
func (d *backend_minio) shutdown() error {
	//fmt.Println("minio.shutdown()")
	var proc = d.get_super_part()
	logger.debugf("Mux(minio) Stopping MinIO: pool=(%s) pid=%d",
		proc.Pool, proc.cmd.Process.Pid)
	//assert_fatal(d.mc_alias != nil)
	var v1 = minio_mc_admin_service_stop(d)
	return v1.err
}

// HEARTBEAT http-gets the path "/minio/health/live" and returns an
// http status code.  It returns 500 on a connection failure.
func (d *backend_minio) heartbeat() int {
	//fmt.Println("minio.heartbeat()")
	var proc = d.get_super_part()

	if d.heartbeat_client == nil {
		var timeout = (time.Duration(proc.Heartbeat_timeout) * time.Second)
		d.heartbeat_client = &http.Client{
			Timeout: timeout,
		}
		var ep = proc.be.Backend_ep
		d.heartbeat_url = fmt.Sprintf("http://%s/minio/health/live", ep)
	}

	var c = d.heartbeat_client
	var rsp, err1 = c.Get(d.heartbeat_url)
	if err1 != nil {
		logger.debugf("Mux(minio) Heartbeat failed (http.Client.Get()):"+
			" pool=(%s) err=(%v)", proc.Pool, err1)
		return http_500_internal_server_error
	}
	defer rsp.Body.Close()
	var _, err2 = io.ReadAll(rsp.Body)
	if err2 != nil {
		logger.infof("Mux(minio) Heartbeat failed (io.ReadAll()):"+
			" pool=(%s) err=(%v)", proc.Pool, err2)
		panic(err2)
	}
	return rsp.StatusCode
}

// *** MC-COMMANDS ***

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

// MINIO_MC_RESULT is a decoding of an output of a MC-command.  On an
// error, it returns {nil,error}.
type minio_mc_result struct {
	values []map[string]any
	err    error
}

// SIMPLIFY_MINIO_MC_MESSAGE returns a 2-tuple {[value,...], ""} on success,
// or {nil, error-cause} on failure.  It extracts a message part from
// an error message.  MC-command may return zero or more values as
// separate json records.  An empty output is a proper success.  Each
// record is {"status": "success", ...}, containing a value.  An error
// record looks like: {"status": "error", "error": {"message":, ...,
// "cause": {"error": {"Code": ..., ...}}}}.  The
// "error/cause/error/Code" slot will be a keyword of useful
// information if it exists.  A returned 2-tuple may have a whole
// message instead of a cause-code if the slot is missing.
func simplify_minio_mc_message(s []byte) *minio_mc_result {
	var mm, ok = decode_json([]string{string(s)})
	if !ok {
		logger.err("Mux(minio) json decode failed")
		var err1 = fmt.Errorf("MC-command returned a bad json: (%s)", s)
		return &minio_mc_result{nil, err1}
	}

	for _, m := range mm {
		switch get_string(m, "status") {
		case "success":
			// Skip.
		case "error":
			if len(mm) != 1 {
				logger.warnf("Mux(minio) MC-command with multiple errors: (%v)", mm)
			}
			var m1 = get_string(m, "error", "cause", "error", "Code")
			if m1 != "" {
				return &minio_mc_result{nil, errors.New(m1)}
			}
			var m2 = get_string(m, "error", "message")
			if m2 != "" {
				return &minio_mc_result{nil, errors.New(m2)}
			}
			return &minio_mc_result{nil, fmt.Errorf("%s", m)}
		default:
			// Unknown status.
			return &minio_mc_result{nil, fmt.Errorf("%s", m)}
		}
	}
	return &minio_mc_result{mm, nil}
}

// EXECUTE_MINIO_MC_CMD runs an MC-command command and checks its output.
// Note that a timeout kills the process by SIGKILL.  MEMO: Timeout of
// context returns "context.deadlineExceededError".
func execute_minio_mc_cmd(d *backend_minio, name string, command []string) *minio_mc_result {
	//var proc = d.get_super_part()
	assert_fatal(d.mc_alias != "" && d.mc_config_dir != "")
	var argv = append([]string{
		d.Mc,
		"--json",
		fmt.Sprintf("--config-dir=%s", d.mc_config_dir)},
		command...)
	var timeout = (time.Duration(d.Backend_command_timeout) * time.Second)
	var ctx, cancel = context.WithTimeout(context.Background(), timeout)
	defer cancel()
	var cmd = exec.CommandContext(ctx, argv[0], argv[1:]...)
	var outb, errb bytes.Buffer
	cmd.Stdin = nil
	cmd.Stdout = &outb
	cmd.Stderr = &errb
	cmd.Env = *d.environ
	var err1 = cmd.Run()
	//fmt.Println("cmd.Run()=", err1)
	switch err2 := err1.(type) {
	case nil:
		// OK.
	case *exec.ExitError:
		// Not successful.
		var status = err2.ProcessState.ExitCode()
		logger.errf("Mux(minio) MC-command failed:"+
			" cmd=(%v) exit=%d error=(%v) stdout=(%s) stderr=(%s)",
			argv, status, err2, outb.String(), errb.String())
	default:
		//fmt.Printf("cmd.Run()=%T %v", err1, err1)
		logger.errf("Mux(minio) MC-command failed:"+
			" cmd=(%v) error=(%v) stdout=(%s) stderr=(%s)",
			argv, err1, outb.String(), errb.String())
	}
	var wstatus = cmd.ProcessState.ExitCode()
	if d.verbose {
		logger.debugf("Mux(minio) MC-command done:"+
			" cmd=(%v) status=%v stdout=(%s) stderr=(%s)",
			argv, wstatus, outb.String(), errb.String())
	}
	if wstatus == -1 {
		logger.errf("Mux(minio) MC-command unfinished:"+
			" cmd=(%v) stdout=(%s) stderr=(%s)",
			argv, outb.String(), errb.String())
		var err3 = fmt.Errorf("MC-command unfinished: (%s)", outb.String())
		return &minio_mc_result{nil, err3}
	}
	var v1 = simplify_minio_mc_message(outb.Bytes())
	if v1.err == nil {
		if d.verbose {
			logger.debugf("Mux(minio) MC-command OK: cmd=(%v)", command)
		} else {
			logger.debugf("Mux(minio) MC-command OK: cmd=(%s)", name)
		}
	} else {
		logger.errf("Mux(minio) MC-command failed:"+
			" cmd=(%v) error=(%v) stdout=(%v) stderr=(%v)",
			argv, v1.err, outb, errb)
	}
	return v1
}

func minio_mc_alias_set(d *backend_minio) *minio_mc_result {
	assert_fatal(d.mc_alias == "" && d.mc_config_dir == "")
	var rnd = strings.ToLower(random_string(12))
	var url = fmt.Sprintf("http://%s", d.be.Backend_ep)
	//d.mc_config_dir = tempfile.TemporaryDirectory()
	var dir, err1 = os.MkdirTemp("", "lens3-mc-")
	if err1 != nil {
		logger.errf("Mux(minio) os.MkdirTemp() failed: err=(%v)", err1)
		return &minio_mc_result{nil, err1}
	}
	d.mc_alias = fmt.Sprintf("pool-%s-%s", d.Pool, rnd)
	d.mc_config_dir = dir
	var v1 = execute_minio_mc_cmd(d, "alias_set",
		[]string{"alias", "set", d.mc_alias, url,
			d.be.Root_access, d.be.Root_secret,
			"--api", "S3v4"})
	if v1.err != nil {
		d.mc_alias = ""
		d.mc_config_dir = ""
	}
	return v1
}

func minio_mc_alias_remove(d *backend_minio) *minio_mc_result {
	assert_fatal(d.mc_alias != "" && d.mc_config_dir != "")
	var v1 = execute_minio_mc_cmd(d, "alias_remove",
		[]string{"alias", "remove", d.mc_alias})
	if v1.err == nil {
		d.mc_alias = ""
		d.mc_config_dir = ""
	}
	return v1
}

func minio_mc_admin_service_stop(d *backend_minio) *minio_mc_result {
	var v1 = execute_minio_mc_cmd(d, "admin_service_stop",
		[]string{"admin", "service", "stop", d.mc_alias})
	return v1
}

func clean_tmp() {
	var d = os.TempDir()
	var pattern = fmt.Sprintf("%s/lens3-mc-*", d)
	var matches, err1 = filepath.Glob(pattern)
	assert_fatal(err1 != nil)
	// (err1 == nil || err1 == filepath.ErrBadPattern)
	for _, p := range matches {
		logger.debugf("Mux(minio) Clean by os.RemoveAll(%s)", p)
		var err2 = os.RemoveAll(p)
		if err2 != nil {
			// (err2 : *os.PathError).
			logger.warnf("Mux(minio) os.RemoveAll(%s) failed: err=(%v)",
				p, err2)
		}
	}
}
