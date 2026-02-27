// Copyright 2022-2026 RIKEN R-CCS
// SPDX-License-Identifier: BSD-2-Clause

// Server Delegate for S3 Baby-server

// S3 Baby-server is at https://github.com/riken-rccs/s3-baby-server

package lens3

import (
	"encoding/json"
	"fmt"
	"net"
	"regexp"
	"runtime"
	"strconv"
	"strings"
)

// Messages Patterns.  These are messages from Baby-server at its
// start-up.  Checking port-in-use matches against the substring
// extracted from the failure message.
var (
	s3baby_date_time_pattern = `\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2}`
	s3baby_url_pattern       = `http://([^:]*|\[[^\]]*\]):([0-9]*)/`

	s3baby_response_expected_re = regexp.MustCompile(
		`^` + date_time_pattern +
			` NOTICE: Local file system at [^:]*:` +
			` Starting s3 server on \[` + url_pattern + `\]$`)

	s3baby_response_s3_failure_re = regexp.MustCompile(
		`^` + date_time_pattern +
			` Failed to s3: (.*)$`)

	s3baby_response_rc_failure_re = regexp.MustCompile(
		`^` + date_time_pattern +
			` Failed to start remote control: (.*)$`)

	s3baby_response_port_in_use_re = regexp.MustCompile(
		`^` + `failed to init server: listen tcp :[0-9]*:` +
			` bind: address already in use$`)

	s3baby_response_control_url_re = regexp.MustCompile(
		`^` + date_time_pattern +
			` NOTICE: Serving remote control on ` +
			url_pattern + `$`)
)

// BACKEND_S3BABY is a manager for Baby-server and implements
// BACKEND_DELEGATE.
type backend_s3baby struct {
	backend_generic

	port       int
	access_key string
	secret_key string

	*s3baby_conf
}

// BACKEND_S3BABY_FACTORY implements BACKEND_FACTORY.
type backend_s3baby_factory struct {
	*s3baby_conf
	backend_conf
}

var the_backend_s3baby_factory = &backend_s3baby_factory{}

func (fa *backend_s3baby_factory) configure(conf *mux_conf) {
	fa.s3baby_conf = conf.S3baby
	fa.backend_conf.use_n_ports = 1
}

func (fa *backend_s3baby_factory) make_delegate(pool string) backend_delegate {
	var d = &backend_s3baby{}
	d.backend_conf = &fa.backend_conf
	d.s3baby_conf = the_backend_s3baby_factory.s3baby_conf
	d.access_key = random_string(10)
	d.secret_key = random_string(20)
	runtime.SetFinalizer(d, finalize_backend_s3baby)
	return d
}

func (fa *backend_s3baby_factory) clean_at_exit() {
}

func finalize_backend_s3baby(d *backend_s3baby) {
}

func (d *backend_s3baby) get_super_part() *backend_generic {
	return &(d.backend_generic)
}

func (d *backend_s3baby) make_command_line(port int, directory string) backend_command {
	d.port = (port + 1)
	var ep1 = net.JoinHostPort("", strconv.Itoa(port))
	//var ep2 = net.JoinHostPort("", strconv.Itoa(port+1))
	var keypair = fmt.Sprintf("%s,%s", d.be.Root_access, d.be.Root_secret)
	var argv = []string{
		d.Path, "serve", ep1, directory,
	}
	if keypair != "" {
		argv = append(argv, "-cred", keypair)
	}
	if true {
		argv = append(argv, "-log", "debug")
		argv = append(argv, "-log-access")
		argv = append(argv, "-prof", "6060")
	}
	argv = append(argv, d.Command_options...)
	var envs = []string{}
	return backend_command{argv, envs}
}

// CHECK_STARTUP decides the server state.  All s3baby's messages at a
// start are on stderr.
func (d *backend_s3baby) check_startup(stream stdio_stream, mm []string) *start_result {
	if stream == on_stdout {
		return &start_result{
			start_state: start_ongoing,
			reason:      pool_reason_NORMAL,
		}
	}
	//fmt.Printf("s3baby.check_startup(%v)\n", mm)

	// Check failure.  Failure messages can be both by S3 and RC.

	var got_s3_failure = s3baby_response_s3_failure_re.MatchString
	var failure_s3_found, m1 = find_one(mm, got_s3_failure)
	if failure_s3_found {
		var r1 = check_s3baby_port_in_use(m1, s3baby_response_s3_failure_re)
		return r1
	}

	var got_rc_failure = s3baby_response_rc_failure_re.MatchString
	var failure_rc_found, m2 = find_one(mm, got_rc_failure)
	if failure_rc_found {
		var r2 = check_s3baby_port_in_use(m2, s3baby_response_rc_failure_re)
		return r2
	}

	// Check an expected message.

	var got_expected = s3baby_response_expected_re.MatchString
	var expected_found, m3 = find_one(mm, got_expected)
	if expected_found {
		var got_control = s3baby_response_control_url_re.MatchString
		var control_found, _ = find_one(mm, got_control)
		if !control_found {
			slogger.Warn("BE(s3baby): Got an expected message" +
				" but no control messages")
		}
		if trace_proc&tracing != 0 {
			slogger.Debug("BE(s3baby): Got an expected message", "output", m3)
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

func check_s3baby_port_in_use(m string, re *regexp.Regexp) *start_result {
	var w1 = re.FindStringSubmatch(m)
	assert_fatal(w1 != nil && len(w1) == 2)
	var port_in_use = s3baby_response_port_in_use_re.MatchString(w1[1])
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

func (d *backend_s3baby) establish() error {
	return nil
}

// SHUTDOWN stops a server using RC core/quit.
func (d *backend_s3baby) shutdown() error {
	var proc = d.get_super_part()
	slogger.Debug("BE(s3baby): Stopping s3baby",
		"pool", proc.Pool, "pid", proc.cmd.Process.Pid)
	var v1 = s3baby_rc_core_quit(d)
	return v1.err
}

// HEARTBEAT calls s3.Client.ListBuckets() and returns a status code.
func (d *backend_s3baby) heartbeat(w *manager) int {
	var proc = d.get_super_part()
	var be = get_backend(w.table, proc.Pool)
	if be == nil {
		return http_404_not_found
	}
	var code = heartbeat_backend(w, be)
	return code
}

// S3BABY_RC_RESULT is a decoding of an output of an RC-command.  On an
// error, it returns {nil,error}.
type s3baby_rc_result struct {
	value map[string]any
	err   error
}

// SIMPLIFY_S3BABY_RC_MESSAGE returns a 2-tuple {value,nil} on
// success, or {nil,err} on failure or decoding error.  An empty
// output "{}" is a proper success.  A failure output looks like
// {"error":message,...}.
func simplify_s3baby_rc_message(s []byte) *s3baby_rc_result {
	var s2 = string(s)
	var r = strings.NewReader(s2)
	var dec = json.NewDecoder(r)
	var m map[string]any
	var err1 = dec.Decode(&m)
	if err1 != nil {
		slogger.Error("BE(s3baby): Bad message from s3baby-rc",
			"output", s2, "err", err1)
		return &s3baby_rc_result{nil, err1}
	}
	switch msg := m["error"].(type) {
	case nil:
		// Okay.
	case string:
		var err2 = fmt.Errorf("%q", msg)
		return &s3baby_rc_result{nil, err2}
	default:
		var err3 = fmt.Errorf("Non-string error message: %q", m)
		slogger.Error("BE(s3baby): Bad message from s3baby-rc",
			"err", err3)
		return &s3baby_rc_result{nil, err3}
	}
	return &s3baby_rc_result{m, nil}
}

// EXECUTE_S3BABY_RC_CMD runs an RC-command and checks its output.
func execute_s3baby_rc_cmd(d *backend_s3baby, synopsis string, command []string) *s3baby_rc_result {
	//var port = net.JoinHostPort("", strconv.Itoa(d.port))
	var argv = []string{}
	argv = append(argv, command...)

	var timeout = (d.Backend_start_timeout_ms).time_duration()
	var verbose = (trace_proc&tracing != 0)
	var stdouts, stderrs, err1 = execute_command(synopsis, argv, d.environ,
		timeout, "BE(s3baby)", verbose)
	if err1 != nil {
		return &s3baby_rc_result{nil, err1}
	}

	var v1 = simplify_s3baby_rc_message([]byte(stdouts))
	if v1.err == nil {
		if trace_proc&tracing != 0 {
			slogger.Debug("BE(s3baby): RC-command Okay",
				"cmd", command)
		} else {
			slogger.Debug("BE(s3baby): RC-command Okay",
				"cmd", synopsis)
		}
	} else {
		slogger.Error("BE(s3baby): RC-command failed",
			"cmd", argv, "err", v1.err,
			"stdout", stdouts, "stderr", stderrs)
	}
	return v1
}

func s3baby_rc_core_quit(d *backend_s3baby) *s3baby_rc_result {
	var v1 = execute_s3baby_rc_cmd(d, "core/quit",
		[]string{"core/quit"})
	return v1
}
