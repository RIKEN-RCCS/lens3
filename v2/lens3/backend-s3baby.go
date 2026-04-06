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
	"log/slog"
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
	delegate_generic
}

// BACKEND_S3BABY_FACTORY implements backend_factory.
type backend_s3baby_factory struct {
	factory_generic
	*s3baby_conf
}

var the_backend_s3baby_factory = &backend_s3baby_factory{}

func (f *backend_s3baby_factory) get_factory_generic_part() *factory_generic {
	return &f.factory_generic
}

func (f *backend_s3baby_factory) configure_factory(conf *mux_conf, wc *manager_conf) {
	f.manager_conf = wc
	f.use_n_ports = 1
	f.s3baby_conf = conf.S3baby
}

func (f *backend_s3baby_factory) make_delegate(pool string) backend_delegate {
	var d = &backend_s3baby{}
	d.factory = f
	runtime.SetFinalizer(d, finalize_backend_s3baby)
	return d
}

func (f *backend_s3baby_factory) clean_at_exit(logger *slog.Logger) {
}

func finalize_backend_s3baby(d *backend_s3baby) {
}

func (d *backend_s3baby) get_factory() *backend_s3baby_factory {
	var f, ok = (d.factory).(*backend_s3baby_factory)
	if !ok {
		logger_0.Error("BE(s3baby): BAD-IMPL backend factory unknown",
			"factory", d.factory)
		panic(nil)
	}
	return f
}

func (d *backend_s3baby) get_delegate_generic_part() *delegate_generic {
	return &d.delegate_generic
}

func (d *backend_s3baby) make_command_line(w *manager, port int, directory string) backend_command {
	var f = d.get_factory()
	var ep1 = net.JoinHostPort("", strconv.Itoa(port))
	var keypair = fmt.Sprintf("%s,%s", d.be.Root_access, d.be.Root_secret)
	var argv = []string{
		f.Path, "serve", ep1, directory,
	}
	if false {
		argv = append(argv, "-log", "debug")
		argv = append(argv, "-log-access")
		argv = append(argv, "-prof", "6060")
	}
	argv = append(argv, f.Command_options...)
	var envs = []string{
		fmt.Sprintf("S3BBS_CRED=%s", keypair),
	}
	return backend_command{argv, envs}
}

// CHECK_STARTUP decides the server state.  It ignores messages on
// stderr.
func (d *backend_s3baby) check_startup(w *manager, stream stdio_stream_indicator, mm []string) *start_result {
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
			w.logger.Debug("BE(s3baby): Got an expected message", "output", m3)
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

func (d *backend_s3baby) establish(w *manager) error {
	return nil
}

// SHUTDOWN stops the server.
func (d *backend_s3baby) shutdown(w *manager) error {
	w.logger.Debug("BE(s3baby): Stopping s3baby",
		"pool", d.Pool, "pid", d.cmd.Process.Pid)
	var _, err1 = control_s3baby_server(d, "quit", w.logger)
	return err1
}

// HEARTBEAT posts an http request to "/bbs.ctl/ping". It returns a
// returned status code, or http_502_bad_gateway (for a client side
// error).
func (d *backend_s3baby) heartbeat(w *manager) int {
	var be = d.be
	if be == nil {
		return http_404_not_found
	}
	if false {
		var _ = heartbeat_backend(w, be)
	}
	var code, _ = control_s3baby_server(d, "ping", w.logger)
	return code
}

// CONTROL_S3BABY_SERVER posts an http request on the control url
// (usually "/bbs.ctl").  It returns a status-code and an error.  It
// returns http_502_bad_gateway, when an error occurs before
// accessing the server.  The commands are: "quit", "stat", or "ping".
// The way to send control messages to Baby-server can be found in
// "test/control/control-client.go" in
// https://github.com/riken-rccs/s3-baby-server
func control_s3baby_server(d *backend_s3baby, command string, logger *slog.Logger) (int, error) {
	if !(command == "quit" || command == "stat" || command == "ping") {
		logger.Error("BE(s3baby): Bad control command",
			"command", command)
		var errx = fmt.Errorf("BE(s3baby): Bad control command: %s", command)
		return http_502_bad_gateway, errx
	}

	var be = d.be
	if be == nil {
		logger.Error("BE(s3baby): No backend record")
		var errx = fmt.Errorf("BE(s3baby): No backend record: pool=%s",
			d.Pool)
		return http_502_bad_gateway, errx
	}

	var keypair = [2]string{be.Root_access, be.Root_secret}

	var f = d.get_factory()
	var control = f.Control

	var timeout = time.Duration(60000 * time.Millisecond)
	var ctx, cancel = context.WithTimeout(context.Background(), timeout)
	defer cancel()

	var ep = be.Backend_ep
	var url1 = ("http://" + ep + "/" + control + "/" + command)
	var body io.Reader = nil

	var r, err4 = http.NewRequestWithContext(ctx, http.MethodPost, url1, body)
	if err4 != nil {
		logger.Debug("BE(s3baby): http.NewRequestWithContext() failed",
			"url", url1, "error", err4)
		return http_502_bad_gateway, err4
	}

	//r.Header.Set("Content-Type", "application/x-www-form-urlencoded")
	var hash = empty_payload_hash_sha256
	r.Header.Set("X-Amz-Content-Sha256", hash)

	var err5 = awss3aide.Sign_by_credential(r, ep, keypair)
	if err5 != nil {
		logger.Warn("BE(s3baby): S3-Signing failed",
			"error", err5)
		return http_502_bad_gateway, err5
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
		logger.Warn("BE(s3baby): http.Client.Do() failed",
			"error", err6)
		return http_502_bad_gateway, err6
	}
	defer rspn.Body.Close()

	if rspn.StatusCode == http_200_OK {
		return http_200_OK, nil
	} else {
		logger.Warn("BE(s3baby): http.Client.Do() returns not OK",
			"status", rspn.StatusCode)
		var err8 = fmt.Errorf("BE(s3baby): http.Client.Do() returns=%d",
			rspn.StatusCode)
		return rspn.StatusCode, err8
	}
}
