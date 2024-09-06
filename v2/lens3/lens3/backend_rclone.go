/* S3 Server Delegate for Rclone "rclone serve s3". */

// Copyright 2022-2024 RIKEN R-CCS
// SPDX-License-Identifier: BSD-2-Clause

package lens3

// This is a backend for rclone.  The target is rclone-v1.66.0.

// MEMO: Starting rclone-serve-s3.
//
// rclone serve s3 '/home/someone/somewhere' [-vvv]
// --addr :{s3port} --auth-key "{id},{key}"
// --rc --rc-addr :{rcport}
// --rc-user {rcuser} --rc-pass {rcpass}
// [--force-path-style true]
// [--vfs-cache-mode full]

// MEMO: Stopping rclone-serve-s3 via a rc-command.
//
// % rclone rc --url :{rcport}
// --user {rcuser} --pass {rcpass} core/quit
//
// Some rc-commands: "core/quit", "job/list"

// MEMO: rc-port default is http://127.0.0.1:5572/
//
// MEMO: Option "--config=notfound" lets not use the rclone.conf file.
// "notfound" is a keyword.
//
// MEMO: vfs caching creates a cache in "~/.cache/rclone", and the
// subdirectories are "vfs/local" and "vfsMeta/local".

import (
	"encoding/json"
	"fmt"
	"net"
	"regexp"
	"runtime"
	"strconv"
	"strings"
)

// Messages Patterns.  These are messages from rclone at its start-up.
// Lens3 avoids using "--use-json-log", since some messages are not in
// json in rclone-v1.66.0.  Checking port-in-use matches against the
// substring extracted from the failure message.
var (
	date_time_pattern = `\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2}`
	url_pattern       = `http://([^:]*|\[[^\]]*\]):([0-9]*)/`

	rclone_response_expected_re = regexp.MustCompile(
		`^` + date_time_pattern +
			` NOTICE: Local file system at [^:]*:` +
			` Starting s3 server on \[` + url_pattern + `\]$`)

	rclone_response_s3_failure_re = regexp.MustCompile(
		`^` + date_time_pattern +
			` Failed to s3: (.*)$`)

	rclone_response_rc_failure_re = regexp.MustCompile(
		`^` + date_time_pattern +
			` Failed to start remote control: (.*)$`)

	rclone_response_port_in_use_re = regexp.MustCompile(
		`^` + `failed to init server: listen tcp :[0-9]*:` +
			` bind: address already in use$`)

	rclone_response_control_url_re = regexp.MustCompile(
		`^` + date_time_pattern +
			` NOTICE: Serving remote control on ` +
			url_pattern + `$`)
)

// BACKEND_RCLONE is a manager for rclone.
type backend_rclone struct {
	backend_generic

	rc_port int
	rc_user string
	rc_pass string

	*rclone_conf
}

// BACKEND_FACTORY_RCLONE.  See "backend_minio.go".
type backend_factory_rclone struct {
	*rclone_conf
	backend_conf
}

var the_backend_rclone_factory = &backend_factory_rclone{}

func (fa *backend_factory_rclone) configure(conf *mux_conf) {
	fa.rclone_conf = &conf.Rclone
	fa.backend_conf.use_n_ports = 2
}

func (fa *backend_factory_rclone) make_delegate(pool string) backend_delegate {
	var d = &backend_rclone{}
	// Set the super part.
	d.backend_conf = &fa.backend_conf
	// Set the local part.
	d.rclone_conf = the_backend_rclone_factory.rclone_conf
	d.rc_user = random_string(10)
	d.rc_pass = random_string(20)
	runtime.SetFinalizer(d, finalize_backend_rclone)
	return d
}

func (fa *backend_factory_rclone) clean_at_exit() {
}

func finalize_backend_rclone(d *backend_rclone) {
}

func (d *backend_rclone) get_super_part() *backend_generic {
	return &(d.backend_generic)
}

func (d *backend_rclone) make_command_line(port int, directory string) backend_command {
	d.rc_port = (port + 1)
	var ep1 = net.JoinHostPort("", strconv.Itoa(port))
	var ep2 = net.JoinHostPort("", strconv.Itoa(port+1))
	var keypair = fmt.Sprintf("%s,%s", d.be.Root_access, d.be.Root_secret)
	var argv = []string{
		d.Rclone, "serve", "s3",
		directory,
		"--config", "notfound",
		"--addr", ep1, "--auth-key", keypair,
		"--rc", "--rc-addr", ep2,
		"--rc-user", d.rc_user, "--rc-pass", d.rc_pass,
	}
	argv = append(argv, d.Command_options...)
	var envs = []string{}
	return backend_command{argv, envs}
}

// CHECK_STARTUP decides the server state.  All rclone's messages at a
// start are on stderr.
func (d *backend_rclone) check_startup(stream stdio_stream, mm []string) *start_result {
	if stream == on_stdout {
		return &start_result{
			start_state: start_ongoing,
			reason:      pool_reason_NORMAL,
		}
	}
	//fmt.Printf("rclone.check_startup(%v)\n", mm)

	// Check failure.  Failure messages can be both by S3 and RC.

	var got_s3_failure = rclone_response_s3_failure_re.MatchString
	var failure_s3_found, m1 = find_one(mm, got_s3_failure)
	if failure_s3_found {
		var r1 = check_rclone_port_in_use(m1, rclone_response_s3_failure_re)
		return r1
	}

	var got_rc_failure = rclone_response_rc_failure_re.MatchString
	var failure_rc_found, m2 = find_one(mm, got_rc_failure)
	if failure_rc_found {
		var r2 = check_rclone_port_in_use(m2, rclone_response_rc_failure_re)
		return r2
	}

	// Check an expected message.

	var got_expected = rclone_response_expected_re.MatchString
	var expected_found, m3 = find_one(mm, got_expected)
	if expected_found {
		var got_control = rclone_response_control_url_re.MatchString
		var control_found, _ = find_one(mm, got_control)
		if !control_found {
			slogger.Warn("BE(rclone): Got an expected message" +
				" but no control messages")
		}
		if trace_proc&tracing != 0 {
			slogger.Debug("BE(rclone): Got an expected message", "output", m3)
		}
		return &start_result{
			start_state: start_started,
			reason:      pool_reason_NORMAL,
		}
	}

	return &start_result{
		start_state: start_ongoing,
		reason:      pool_reason_NORMAL,
	}
}

func check_rclone_port_in_use(m string, re *regexp.Regexp) *start_result {
	var w1 = re.FindStringSubmatch(m)
	assert_fatal(w1 != nil && len(w1) == 2)
	var port_in_use = rclone_response_port_in_use_re.MatchString(w1[1])
	if port_in_use {
		return &start_result{
			start_state: start_to_retry,
			reason:      pool_reason_NORMAL,
		}
	} else {
		return &start_result{
			start_state: start_persistent_failure,
			reason:      make_failure_reason(m),
		}
	}
}

func (d *backend_rclone) establish() error {
	return nil
}

// SHUTDOWN stops a server using RC core/quit.
func (d *backend_rclone) shutdown() error {
	var proc = d.get_super_part()
	slogger.Debug("BE(rclone): Stopping rclone",
		"pool", proc.Pool, "pid", proc.cmd.Process.Pid)
	var v1 = rclone_rc_core_quit(d)
	return v1.err
}

// HEARTBEAT calls s3.Client.ListBuckets() and returns a status code.
func (d *backend_rclone) heartbeat(w *manager) int {
	var proc = d.get_super_part()
	var be = get_backend(w.table, proc.Pool)
	if be == nil {
		return http_404_not_found
	}
	var code = heartbeat_backend(w, be)
	return code
}

// RCLONE_RC_RESULT is a decoding of an output of an RC-command.  On an
// error, it returns {nil,error}.
type rclone_rc_result struct {
	value map[string]any
	err   error
}

// SIMPLIFY_RCLONE_RC_MESSAGE returns a 2-tuple {value,nil} on
// success, or {nil,err} on failure or decoding error.  An empty
// output "{}" is a proper success.  A failure output looks like
// {"error":message,...}.
func simplify_rclone_rc_message(s []byte) *rclone_rc_result {
	var s2 = string(s)
	var r = strings.NewReader(s2)
	var dec = json.NewDecoder(r)
	var m map[string]any
	var err1 = dec.Decode(&m)
	if err1 != nil {
		slogger.Error("BE(rclone): Bad message from rclone-rc",
			"output", s2, "err", err1)
		return &rclone_rc_result{nil, err1}
	}
	switch msg := m["error"].(type) {
	case nil:
		// Okay.
	case string:
		var err2 = fmt.Errorf("%q", msg)
		return &rclone_rc_result{nil, err2}
	default:
		var err3 = fmt.Errorf("Non-string error message: %q", m)
		slogger.Error("BE(rclone): Bad message from rclone-rc",
			"err", err3)
		return &rclone_rc_result{nil, err3}
	}
	return &rclone_rc_result{m, nil}
}

// EXECUTE_RCLONE_RC_CMD runs an RC-command and checks its output.
func execute_rclone_rc_cmd(d *backend_rclone, synopsis string, command []string) *rclone_rc_result {
	var port = net.JoinHostPort("", strconv.Itoa(d.rc_port))
	var argv = []string{
		d.Rclone, "rc",
		"--url", port,
		"--user", d.rc_user,
		"--pass", d.rc_pass,
	}
	argv = append(argv, command...)

	var timeout = (d.Backend_start_timeout_ms).time_duration()
	var verbose = (trace_proc&tracing != 0)
	var stdouts, stderrs, err1 = execute_command(synopsis, argv, d.environ,
		timeout, "BE(rclone)", verbose)
	if err1 != nil {
		return &rclone_rc_result{nil, err1}
	}

	var v1 = simplify_rclone_rc_message([]byte(stdouts))
	if v1.err == nil {
		if trace_proc&tracing != 0 {
			slogger.Debug("BE(rclone): RC-command Okay",
				"cmd", command)
		} else {
			slogger.Debug("BE(rclone): RC-command Okay",
				"cmd", synopsis)
		}
	} else {
		slogger.Error("BE(rclone): RC-command failed",
			"cmd", argv, "err", v1.err,
			"stdout", stdouts, "stderr", stderrs)
	}
	return v1
}

func rclone_rc_core_quit(d *backend_rclone) *rclone_rc_result {
	var v1 = execute_rclone_rc_cmd(d, "core/quit",
		[]string{"core/quit"})
	return v1
}
