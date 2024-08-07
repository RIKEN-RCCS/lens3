/* Docstring of lens3 package. */

// Copyright 2022-2024 RIKEN R-CCS
// SPDX-License-Identifier: BSD-2-Clause

// Lens3 service consists of three sub-services, Multiplexer (Mux),
// Manager, and Registrar (Reg).  Lens3 also has Admintool command.
// Multiplexer is a proxy, Manager is a sentinel of backend servers,
// and Registrar is a web-api to setup buckets and access-keys by
// users.  Manager is a supporting service for Multiplexer.  They
// could be three programs, but they are by threads.  In the
// implementation, they share nothing but communicate via the
// keyval-db.
package lens3

// GOLANG VERSIONS: "slices" is from v1.22.  Note Golang is v1.21
// in Linux Rocky8/9 as of 2024-04-01.

// Golang prefers "x/sys/unix" over "syscall".  "SysProcAttr" are
// the same in "x/sys/unix" and "syscall".

// "log/slog" is in Go1.21.
