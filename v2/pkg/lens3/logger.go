/* Dummy of syslog. */

// Copyright 2022-2024 RIKEN R-CCS
// SPDX-License-Identifier: BSD-2-Clause

package lens3

// Logger wrapper like syslog but outputs to stdout.

import (
	"fmt"
	"log"
	"net/http"
	"os"
	"time"
)

// var logger = slog.Default()
// var logger = syslog.New()
var logger = logger_default()

type log_writer struct {
	o *log.Logger
}

func logger_default() *log_writer {
	return &log_writer{
		o: log.New(os.Stdout, "", log.LstdFlags),
	}
}

func (w *log_writer) critf(f string, a ...any) error {
	return w.crit(fmt.Sprintf(f, a...))
}

func (w *log_writer) crit(m string) error {
	w.o.Printf("CRIT %s", m)
	return nil
}

func (w *log_writer) errf(f string, a ...any) error {
	return w.err(fmt.Sprintf(f, a...))
}

func (w *log_writer) err(m string) error {
	w.o.Printf("ERR %s", m)
	return nil
}

func (w *log_writer) warnf(f string, a ...any) error {
	return w.warn(fmt.Sprintf(f, a...))
}

func (w *log_writer) warn(m string) error {
	w.o.Printf("WARNING %s", m)
	return nil
}

func (w *log_writer) noticef(f string, a ...any) error {
	return w.notice(fmt.Sprintf(f, a...))
}

func (w *log_writer) notice(m string) error {
	w.o.Printf("NOTICE %s", m)
	return nil
}

func (w *log_writer) infof(f string, a ...any) error {
	return w.info(fmt.Sprintf(f, a...))
}

func (w *log_writer) info(m string) error {
	w.o.Printf("INFO %s", m)
	return nil
}

func (w *log_writer) debugf(f string, a ...any) error {
	return w.debug(fmt.Sprintf(f, a...))
}

func (w *log_writer) debug(m string) error {
	w.o.Printf("DEBUG %s", m)
	return nil
}

func log_access_by_request(r *http.Request, code int) {
	logger.infof("access code=%d", code)
}

// MEMO: Apache httpd access log format:
//
// LogFormat %h %l %u %t "%r" %>s %b "%{Referer}i" "%{User-Agent}i" combined
//
// https://en.wikipedia.org/wiki/Common_Log_Format
//
//  10.128.8.30 - - [04/Mar/2024:17:43:20 +0900] "GET /... HTTP/1.1"
//  403 403 "-" "aws-cli/1.18.156 Python/3.6.8
//  Linux/4.18.0-513.18.1.el8_9.x86_64 botocore/1.18.15"

func log_access(rspn *http.Response) {
	var req = rspn.Request
	//fmt.Printf("*** ACCESS_LOGGING Response=%#v\n", rspn)
	//fmt.Printf("*** ACCESS_LOGGING Request=%#v\n", req)

	var layout = "02/Jan/2006:15:04:05 -0700"

	// l: RFC 1413 client identity by identd
	// (RFC 1413 : "Identification Protocol")
	// u: user
	// rf: Referer

	var h = req.RemoteAddr
	var l = "-"
	var u = "-"
	var t = time.Now().Format(layout)
	var r = fmt.Sprintf("%s %s %s", req.Method, req.URL, req.Proto)
	var s = fmt.Sprintf("%d", rspn.StatusCode)
	var b = fmt.Sprintf("%d", rspn.ContentLength)
	var rf = "-"
	var ua = req.Header.Get("User-Agent")

	logger.infof((`%s %s %s [%s] "%s"` + ` %s %s "%s" "%s"`),
		h, l, u, t, r,
		s, b, rf, ua)
}
