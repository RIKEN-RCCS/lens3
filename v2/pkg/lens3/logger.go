/* Dummy of syslog. */

// Copyright 2022-2024 RIKEN R-CCS
// SPDX-License-Identifier: BSD-2-Clause

// Logger wrapper like syslog but outputs to stdout.

package lens3

import (
	"fmt"
	"log"
	"os"
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

func (w *log_writer) errorf(f string, a ...any) error {
	return w.error(fmt.Sprintf(f, a...))
}

func (w *log_writer) error(m string) error {
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
