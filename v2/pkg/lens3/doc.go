/* Docstring of lens3 package. */

// Copyright 2022-2024 RIKEN R-CCS
// SPDX-License-Identifier: BSD-2-Clause

// Lens3 implementation.  Lens3 service consists of three
// sub-services, Multiplexer (Mux), Manager, and Registrar (Api).
// Multiplexer is a proxy, Manager is a sentinel of backend servers,
// and Registrar is a web-service to setup buckets and access-keys by
// users.  They could be three programs, but they are by threads.  In
// the implementaion, they share nothing but communicate via a
// key-value store.
package lens3
