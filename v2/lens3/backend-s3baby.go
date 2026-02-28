// Copyright 2022-2026 RIKEN R-CCS
// SPDX-License-Identifier: BSD-2-Clause

// Backend Delegate for S3 Baby-server

// Baby-server is at https://github.com/riken-rccs/s3-baby-server

// Baby-server prints messages in "slog" logging format.  Typical
// start-up failure is port-in-use or bad-directory.
//
// [successful case]
// time=2026-02-28T07:39:17.895Z level=INFO msg="Starting Baby-server"
//   address=127.0.0.1:9000 proto=http access-key=s3baby version=v1.2.1
//
// [error case: port-in-use]
// time=2026-02-28T07:37:37.409Z level=ERROR msg="net.Listen() failed"
//   address=127.0.0.1:9000 error="listen tcp 127.0.0.1:9000: bind: address
//   already in use"
//
// [error case: bad-directory]
// time=2026-02-27T14:00:21.297Z level=ERROR msg="os.Chdir() to pool
//   directory failed" directory=/bad-dir error="chdir /bad-dir: no
//   such file or directory"

package lens3

import (
	"context"
	"crypto/tls"
	"fmt"
	"io"
	"net"
	"net/http"
	"regexp"
	"runtime"
	"strconv"
	"strings"
	"time"

	"github.com/riken-rccs/s3-baby-server/pkg/awss3aide"
	"github.com/riken-rccs/s3-baby-server/pkg/quotedstring"
)

// Messages Patterns.  Checking port-in-use is to match against the
// usual message.
var (
	s3baby_response_port_in_use_re = regexp.MustCompile(
		`bind: address already in use`)
)

// BACKEND_S3BABY is a manager for Baby-server and implements
// backend_delegate.
type backend_s3baby struct {
	backend_generic
	conf *backend_s3baby_factory
}

// BACKEND_S3BABY_FACTORY implements backend_factory.
type backend_s3baby_factory struct {
	factory_generic
	*s3baby_conf
}

var the_backend_s3baby_factory = &backend_s3baby_factory{}

func (f *backend_s3baby_factory) configure(conf *mux_conf) {
	f.s3baby_conf = conf.S3baby
	f.use_n_ports = 1
}

func (f *backend_s3baby_factory) make_delegate(pool string) backend_delegate {
	var d = &backend_s3baby{}
	d.conf = f
	runtime.SetFinalizer(d, finalize_backend_s3baby)
	return d
}

func (f *backend_s3baby_factory) clean_at_exit() {
}

func finalize_backend_s3baby(d *backend_s3baby) {
}

func (d *backend_s3baby) get_super_part() *backend_generic {
	return &(d.backend_generic)
}

func (d *backend_s3baby) make_command_line(port int, directory string) backend_command {
	var ep1 = net.JoinHostPort("", strconv.Itoa(port))
	var keypair = fmt.Sprintf("%s,%s", d.be.Root_access, d.be.Root_secret)
	var argv = []string{
		d.conf.Path, "serve", ep1, directory,
	}
	if false {
		argv = append(argv, "-log", "debug")
		argv = append(argv, "-log-access")
		argv = append(argv, "-prof", "6060")
	}
	argv = append(argv, d.conf.Command_options...)
	var envs = []string{
		fmt.Sprintf("S3BBS_CRED=%s", keypair),
	}
	return backend_command{argv, envs}
}

// CHECK_STARTUP decides the server state.  It ignores messages on
// stderr.
func (d *backend_s3baby) check_startup(stream stdio_stream_indicator, mm []string) *start_result {
	if stream == on_stderr {
		return &start_result{
			start_state: start_ongoing,
			reason:      pool_reason_NORMAL,
		}
	}

	var msgs = convert_s3baby_logging(mm)

	fmt.Printf("s3baby.check_startup(%v)\n", msgs)

	// Check failure.

	var failure_found, m1 = find_one(msgs, got_s3baby_error)
	if failure_found {
		var r1 = got_s3baby_port_in_use(m1)
		return r1
	}

	// Check an expected message.

	var expected_found, m3 = find_one(msgs, got_s3baby_expected)
	if expected_found {
		if trace_proc&tracing != 0 {
			slogger.Debug("BE(s3baby): Got an expected message", "output", m3)
		}
		return &start_result{
			start_state: start_started,
			reason:      pool_reason_NORMAL,
		}
	}

	// Otherwise.

	return &start_result{
		start_state: start_ongoing,
		reason:      pool_reason_NORMAL,
	}
}

func convert_s3baby_logging(mm []string) []map[string]string {
	var acc []map[string]string
	var m string
	for _, m = range mm {
		if !strings.HasPrefix(m, "time=") {
			// Ignore an ill-formed log entry.
			continue
		}
		var mm, err1 = quotedstring.Slog_parse(m)
		if err1 != nil {
			// Ignore an ill-formed log entry.
			continue
		}
		var kv = make(map[string]string)
		for _, e := range mm {
			kv[e[0]] = e[1]
		}
		acc = append(acc, kv)
	}
	return acc
}

func got_s3baby_expected(kv map[string]string) bool {
	if kv["level"] == "INFO" && kv["msg"] == "Starting Baby-server" {
		return true
	} else {
		return false
	}
}

func got_s3baby_error(kv map[string]string) bool {
	if kv["level"] == "ERROR" {
		return true
	} else {
		return false
	}
}

func got_s3baby_port_in_use(kv map[string]string) *start_result {
	var m = kv["error"]
	var re = s3baby_response_port_in_use_re
	var w1 = re.FindStringSubmatch(m)
	if w1 != nil {
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

// SHUTDOWN stops the server.
func (d *backend_s3baby) shutdown() error {
	slogger.Debug("BE(s3baby): Stopping s3baby",
		"pool", d.Pool, "pid", d.cmd.Process.Pid)
	var v1 = control_s3baby_server(d, "quit")
	return v1
}

// HEARTBEAT calls s3.Client.ListBuckets() and returns a status code.
func (d *backend_s3baby) heartbeat(w *manager) int {
	//var proc = d.get_super_part()
	var be = d.be
	if be == nil {
		return http_404_not_found
	}
	var code = heartbeat_backend(w, be)
	return code
}

// A way to send control messages to Baby-server can be found in
// "test/control/control-client.go" in
// https://github.com/riken-rccs/s3-baby-server

func control_s3baby_server(d *backend_s3baby, command string) error {
	if !(command == "quit" || command == "stat") {
		slogger.Error("BE(s3baby): Bad control command",
			"command", command)
		var errx = fmt.Errorf("BE(s3baby): Bad control command: %s", command)
		return errx
	}

	var be = d.be
	if be == nil {
		slogger.Error("BE(s3baby): No backend record")
		var errx = fmt.Errorf("BE(s3baby): No backend record: pool=%s",
			d.Pool)
		return errx
	}

	var cred = [2]string{be.Root_access, be.Root_secret}

	var timeout = time.Duration(60000 * time.Millisecond)
	var ctx, cancel = context.WithTimeout(context.Background(), timeout)
	defer cancel()

	var ep = be.Backend_ep
	var host, _, err1 = net.SplitHostPort(ep)
	if err1 != nil {
		slogger.Error("BE(s3baby): net.SplitHostPort() on backend-ep failed",
			"ep", ep, "error", err1)
		return err1
	}

	var url1 = (ep + "/bbs.ctl/" + command)
	var body io.Reader = nil

	var r, err4 = http.NewRequestWithContext(ctx, http.MethodPost, url1, body)
	if err4 != nil {
		slogger.Debug("BE(s3baby): http.NewRequestWithContext() failed",
			"url", url1, "error", err4)
		return err4
	}

	//r.Header.Set("Content-Type", "application/x-www-form-urlencoded")
	var hash = empty_payload_hash_sha256
	r.Header.Set("X-Amz-Content-Sha256", hash)

	var err5 = awss3aide.Sign_by_credential(r, host, cred)
	if err5 != nil {
		slogger.Warn("BE(s3baby): S3-Signing failed",
			"error", err5)
		return err5
	}

	// Set to skip https server certificate verification.

	var xport = &http.Transport{
		TLSClientConfig: &tls.Config{InsecureSkipVerify: true},
	}
	var c = &http.Client{
		Transport: xport,
		Timeout:   timeout,
	}
	var rspn, err6 = c.Do(r)
	if err6 != nil {
		slogger.Warn("BE(s3baby): http.Client.Do() failed",
			"error", err6)
		return err6
	}
	defer rspn.Body.Close()

	if rspn.StatusCode == http.StatusOK {
		return nil
	} else {
		slogger.Warn("BE(s3baby): http.Client.Do() returns not OK",
			"status", rspn.StatusCode)
		var err8 = fmt.Errorf("BE(s3baby): http.Client.Do() returns=%d",
			rspn.StatusCode)
		return err8
	}

	return nil
}
