/* Docstring of lens3 package. */

// Copyright 2022-2024 RIKEN R-CCS
// SPDX-License-Identifier: BSD-2-Clause

// Lens3 service consists of three sub-services, Multiplexer (Mux),
// Manager, and Registrar (Reg).  Lens3 also has Administrator tool
// (lens3-admin).  Multiplexer is a proxy, Manager is a sentinel of
// backend servers, and Registrar is a Web-API to register buckets and
// access-keys by users.  Manager is a part of Multiplexer.
// Multiplexer and Registrar are a single binary and work in threads.
// They can be started as separate services.  Multiplexer and
// Registrar share nothing but via the keyval-db.
package lens3

// Package versions are fixed on 2024-08-20.  Golang version
// go-1.22.6.  valkey-7.2.6.

// Lens3 is for Golang v1.22 and later because "slices" is from v1.22.
// "log/slog" is from v1.21.  Note Golang is v1.21 in Linux Rocky8/9
// as of 2024-08-20.
//
// Golang prefers "x/sys/unix" over "syscall".  "SysProcAttr" are
// the same in "x/sys/unix" and "syscall".
