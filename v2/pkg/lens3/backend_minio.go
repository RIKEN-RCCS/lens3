/* S3 Server Delegate for MinIO. */

// Copyright 2022-2024 RIKEN R-CCS
// SPDX-License-Identifier: BSD-2-Clause

package lens3

import (
	"errors"
	"fmt"
	"io"
	"net"
	"net/http"
	"os"
	"path/filepath"
	"runtime"
	"strconv"
	"strings"
	"time"
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

// BACKEND_MINIO is a delegate for MinIO.
type backend_minio struct {
	backend_generic

	mc_alias      string
	mc_config_dir string

	heartbeat_client *http.Client
	heartbeat_url    string

	*minio_conf
}

// BACKEND_FACTORY_MINIO is a factory and holds the static and common
// part of a MinIO backend.
type backend_factory_minio struct {
	*minio_conf
	backend_conf
}

var the_backend_minio_factory = &backend_factory_minio{}

func (fa *backend_factory_minio) configure(conf *mux_conf) {
	fa.minio_conf = &conf.Minio
	fa.backend_conf.use_n_ports = 1
}

func (fa *backend_factory_minio) make_delegate(pool string) backend_delegate {
	var d = &backend_minio{}
	// Set the super part.
	d.backend_conf = &fa.backend_conf
	// Set the local part.
	d.minio_conf = the_backend_minio_factory.minio_conf
	runtime.SetFinalizer(d, finalize_backend_minio)
	return d
}

func (fa *backend_factory_minio) clean_at_exit() {
	clean_minio_tmp()
}

func finalize_backend_minio(d *backend_minio) {
	if d.mc_config_dir != "" {
		os.RemoveAll(d.mc_config_dir)
		d.mc_config_dir = ""
	}
}

func (d *backend_minio) get_super_part() *backend_generic {
	return &(d.backend_generic)
}

func (d *backend_minio) make_command_line(port int, directory string) backend_command {
	var ep = net.JoinHostPort("", strconv.Itoa(port))
	var argv = []string{
		d.Minio,
		"--json", "--anonymous", "server",
		"--address", ep, directory}
	var envs = []string{
		fmt.Sprintf("MINIO_ROOT_USER=%s", d.be.Root_access),
		fmt.Sprintf("MINIO_ROOT_PASSWORD=%s", d.be.Root_secret),
		fmt.Sprintf("MINIO_BROWSER=%s", "off"),
	}
	return backend_command{argv, envs}
}

// CHECK_STARTUP decides the server state.  It looks for an expected
// response, when no messages are "level=FATAL".  Otherwise, in case
// of an error with messages "level=FATAL", it diagnoses the cause of
// the error by the first fatal message.  It returns a retry response
// only on the port-in-use error.
func (d *backend_minio) check_startup(stream stdio_stream, ss []string) *start_result {
	//fmt.Println("minio.check_startup(%v)", ss)
	if stream == on_stderr {
		return &start_result{
			start_state: start_ongoing,
			message:     "--",
		}
	}
	var mm, _ = decode_json(ss)
	//fmt.Printf("mm=%T\n", mm)
	if len(mm) == 0 {
		return &start_result{
			start_state: start_ongoing,
			message:     "--",
		}
	}
	// var m1, fatal1 = check_fatal_exists(mm)
	var error_found, m1 = find_one(mm, has_level_fatal)
	if error_found {
		assert_fatal(m1 != nil)
		var msg = get_string(m1, "message")
		switch {
		case strings.HasPrefix(msg, minio_response_port_in_use):
			return &start_result{
				start_state: start_to_retry,
				message:     msg,
			}
		default:
			return &start_result{
				start_state: start_failure,
				message:     msg,
			}
		}
	}
	// var m2, expected1 = check_expected_exists(mm)
	var expected_found, m2 = find_one(mm, has_expected_response)
	if expected_found {
		assert_fatal(m2 != nil)
		var m3 = get_string(m2, "message")
		if d.verbose {
			slogger.Debug("BE(minio): Got an expected message", "output", m3)
		}
		return &start_result{
			start_state: start_started,
			message:     m3,
		}
	}
	return &start_result{
		start_state: start_ongoing,
		message:     "--",
	}
}

func (d *backend_minio) establish() error {
	//fmt.Println("minio.establish()")
	var v1 = minio_mc_alias_set(d)
	return v1.err
}

// SHUTDOWN stops a server using MC admin-service-stop.
func (d *backend_minio) shutdown() error {
	//fmt.Println("minio.shutdown()")
	var proc = d.get_super_part()
	slogger.Debug("BE(minio): Stopping MinIO",
		"pool", proc.Pool, "pid", proc.cmd.Process.Pid)
	//assert_fatal(d.mc_alias != nil)
	var v1 = minio_mc_admin_service_stop(d)
	return v1.err
}

// HEARTBEAT http-gets the path "/minio/health/live" and returns an
// http status code.  It returns 500 on a connection failure.
func (d *backend_minio) heartbeat(*manager) int {
	//fmt.Println("minio.heartbeat()")
	var proc = d.get_super_part()

	if d.heartbeat_client == nil {
		var timeout = (time.Duration(proc.Backend_timeout_ms) * time.Millisecond)
		d.heartbeat_client = &http.Client{
			Timeout: timeout,
		}
		var ep = proc.be.Backend_ep
		d.heartbeat_url = fmt.Sprintf("http://%s/minio/health/live", ep)
	}

	var c = d.heartbeat_client
	var rsp, err1 = c.Get(d.heartbeat_url)
	if err1 != nil {
		slogger.Info("BE(minio): Heartbeat failed in http/Client.Get()",
			"pool", proc.Pool, "err", err1)
		return http_500_internal_server_error
	}
	defer rsp.Body.Close()
	var _, err2 = io.ReadAll(rsp.Body)
	if err2 != nil {
		slogger.Info("BE(minio): Heartbeat failed in io/ReadAll()",
			"pool", proc.Pool, "err", err2)
		return http_500_internal_server_error
	}
	return rsp.StatusCode
}

// *** MC-COMMANDS ***

// Note It works with a missing key, because fetching a missing key
// from a map returns a zero-value.
func has_level_fatal(m map[string]any) bool {
	return (m["level"] == "FATAL")
}

func has_expected_response(m map[string]any) bool {
	var s = get_string(m, "message")
	return strings.HasPrefix(s, minio_expected_response)
}

// MINIO_MC_RESULT is a decoding of an output of an MC-command.  On an
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
		slogger.Error("BE(minio): json decode failed")
		var err1 = fmt.Errorf("MC-command returned a bad json: %q", s)
		return &minio_mc_result{nil, err1}
	}

	for _, m := range mm {
		switch get_string(m, "status") {
		case "success":
			// Skip.
		case "error":
			if len(mm) != 1 {
				slogger.Warn("BE(minio): MC-command with multiple errors",
					"stdout", mm)
			}
			var m1 = get_string(m, "error", "cause", "error", "Code")
			if m1 != "" {
				return &minio_mc_result{nil, errors.New(m1)}
			}
			var m2 = get_string(m, "error", "message")
			if m2 != "" {
				return &minio_mc_result{nil, errors.New(m2)}
			}
			return &minio_mc_result{nil, fmt.Errorf("%q", m)}
		default:
			// Unknown status.
			return &minio_mc_result{nil, fmt.Errorf("%q", m)}
		}
	}
	return &minio_mc_result{mm, nil}
}

// EXECUTE_MINIO_MC_CMD runs an MC-command and checks its output.
func execute_minio_mc_cmd(d *backend_minio, synopsis string, command []string) *minio_mc_result {
	assert_fatal(d.mc_alias != "" && d.mc_config_dir != "")
	var argv = []string{
		d.Mc,
		"--json",
		fmt.Sprintf("--config-dir=%s", d.mc_config_dir),
	}
	argv = append(argv, command...)

	var timeout = (time.Duration(d.Backend_start_timeout_ms) * time.Millisecond)
	var stdouts, stderrs, err1 = execute_command(synopsis, argv, d.environ,
		timeout, "BE(minio)", d.verbose)
	if err1 != nil {
		return &minio_mc_result{nil, err1}
	}

	var v1 = simplify_minio_mc_message([]byte(stdouts))
	if v1.err == nil {
		if d.verbose {
			slogger.Debug("BE(minio): MC-command Okay", "cmd", command)
		} else {
			slogger.Debug("BE(minio): MC-command Okay", "cmd", synopsis)
		}
	} else {
		slogger.Error("BE(minio): MC-command failed",
			"cmd", argv, "err", v1.err,
			"stdout", stdouts, "stderr", stderrs)
	}
	return v1
}

func minio_mc_alias_set(d *backend_minio) *minio_mc_result {
	assert_fatal(d.mc_alias == "" && d.mc_config_dir == "")
	var rnd = strings.ToLower(random_string(12))
	var url = fmt.Sprintf("http://%s", d.be.Backend_ep)
	var dir, err1 = os.MkdirTemp("", "lens3-mc-")
	if err1 != nil {
		slogger.Error("BE(minio): os/MkdirTemp() failed", "err", err1)
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

func clean_minio_tmp() {
	var d = os.TempDir()
	var pattern = fmt.Sprintf("%s/lens3-mc-*", d)
	var matches, err1 = filepath.Glob(pattern)
	if err1 != nil {
		// (err1 : filepath.ErrBadPattern).
		slogger.Error("BE(minio): filepath/Glob() failed",
			"pattern", pattern, "err", err1)
		return
	}
	for _, p := range matches {
		slogger.Debug("BE(minio): Clean by os/RemoveAll()", "path", p)
		var err2 = os.RemoveAll(p)
		if err2 != nil {
			// (err2 : *os.PathError).
			slogger.Error("BE(minio): os/RemoveAll() failed",
				"path", p, "err", err2)
		}
	}
}
