/* Pool Data. */

// Copyright 2022-2024 RIKEN R-CCS.
// SPDX-License-Identifier: BSD-2-Clause

package lens3

import (
//"fmt"
//"flag"
//"context"
//"io"
//"log"
//"os"
//"net"
//"net/http"
//"net/http/httputil"
//"net/url"
//"strings"
//"time"
//"runtime"
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
