/* Pool Data. */

// Copyright 2022-2024 RIKEN R-CCS.
// SPDX-License-Identifier: BSD-2-Clause

package lens3

import (
// "fmt"
// "flag"
// "context"
// "io"
// "log"
// "os"
// "net"
// "net/http"
// "net/http/httputil"
// "net/url"
// "strings"
// "time"
// "runtime"
)

// Key_Policy is a policy to an access-key.
type Key_Policy string

const (
	Key_Policy_READWRITE Key_Policy = "readwrite"
	Key_Policy_READONLY  Key_Policy = "readonly"
	Key_Policy_WRITEONLY Key_Policy = "writeonly"
)

// Bkt_Policy is a public-access policy of a bucket
type Bkt_Policy string

const (
	Bkt_Policy_NONE     Bkt_Policy = "none"
	Bkt_Policy_UPLOAD   Bkt_Policy = "upload"
	Bkt_Policy_DOWNLOAD Bkt_Policy = "download"
	Bkt_Policy_PUBLIC   Bkt_Policy = "public"
)

// Pool_State is a state of a pool.
type Pool_State string

const (
	Pool_State_INITIAL    Pool_State = "initial"
	Pool_State_READY      Pool_State = "ready"
	Pool_State_SUSPENDED  Pool_State = "suspended"
	Pool_State_DISABLED   Pool_State = "disabled"
	Pool_State_INOPERABLE Pool_State = "inoperable"
)

// POOL_REASON is a set of constant strings of the reasons of state
// transitions.  It may include other messages from a backend server.
// POOL_REMOVED is not stored in the state of a pool.  EXEC_FAILED and
// SETUP_FAILED will be appended to another reason.
type Pool_Reason string

const (
	// Pool_State.INITIAL or Pool_State.READY.
	Pool_Reason_NORMAL Pool_Reason = "-"

	// Pool_State.SUSPENDED.
	Pool_Reason_BACKEND_BUSY Pool_Reason = "backend busy"

	// Pool_State.DISABLED.
	Pool_Reason_POOL_EXPIRED  Pool_Reason = "pool expired"
	Pool_Reason_USER_DISABLED Pool_Reason = "user disabled"
	Pool_Reason_POOL_OFFLINE  Pool_Reason = "pool offline"

	// Pool_State.INOPERABLE.
	Pool_Reason_POOL_REMOVED Pool_Reason = "pool removed"
	Pool_Reason_USER_REMOVED Pool_Reason = "user removed"
	Pool_Reason_EXEC_FAILED  Pool_Reason = "start failed: "
	Pool_Reason_SETUP_FAILED Pool_Reason = "initialization failed: "

	// Other reasons are exceptions and messages from a backend.

	Pool_Reason_POOL_DISABLED_INITIALLY_ Pool_Reason = "pool disabled initially"
)
