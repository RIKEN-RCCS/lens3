/* Dummy of syslog. */

// Copyright 2022-2024 RIKEN R-CCS
// SPDX-License-Identifier: BSD-2-Clause

// Logger wrapper like syslog but outputs to stdout.

package lens3

import (
	"log"
	"os"
)

type log_writer struct {
	o *log.Logger
}

func logger_default() *log_writer {
	return &log_writer{
		o: log.New(os.Stdout, "", log.LstdFlags),
	}
}

func (w *log_writer) Err(m string) error {
	w.o.Printf("ERR %s", m)
	return nil
}

func (w *log_writer) Warning(m string) error {
	w.o.Printf("WARNING %s", m)
	return nil
}

func (w *log_writer) Notice(m string) error {
	w.o.Printf("NOTICE %s", m)
	return nil
}

func (w *log_writer) Info(m string) error {
	w.o.Printf("INFO %s", m)
	return nil
}

func (w *log_writer) Debug(m string) error {
	w.o.Printf("DEBUG %s", m)
	return nil
}
