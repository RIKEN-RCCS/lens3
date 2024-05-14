/* Lens3-Api.  It is a pool mangement. */

// Copyright 2022-2024 RIKEN R-CCS
// SPDX-License-Identifier: BSD-2-Clause

package lens3

import ()

//{policy: "readwrite", keys: pool_data.secrets_rw},
//{policy: "readonly", keys: pool_data.secrets_ro},
//{policy: "writeonly", keys: pool_data.secrets_wo},

// RESPONSE_TO_UI is json format of the response to UI.  See also the
// function set_pool_data() in "v1/ui/src/lens3c.ts".
type response_to_ui struct {
	Pool_desc pool_desc_ui `json:"pool_desc"`
}

// POOL_DESC_UI is a subfield of response_to_ui.
type pool_desc_ui struct {
	Pool_name           string           `json:"pool_name"`
	Buckets_directory   string           `json:"buckets_directory"`
	Owner_uid           string           `json:"owner_uid"`
	Owner_gid           string           `json:"owner_gid"`
	Buckets             []bucket_desc_ui `json:"buckets"`
	Secrets             []secret_desc_ui `json:"secrets"`
	Probe_key           string           `json:"probe_key"`
	Expiration_time     int64            `json:"expiration_time"`
	Online_status       string           `json:"online_status"`
	User_enabled_status bool             `json:"user_enabled_status"`
	Minio_state         string           `json:"minio_state"`
	Minio_reason        string           `json:"minio_reason"`
	Modification_time   int64            `json:"modification_time"`
}

type bucket_desc_ui struct {
	Name              string `json:"name"`
	Pool              string `json:"pool"`
	Bkt_policy        string `json:"bkt_policy"`
	Modification_time int64  `json:"modification_time"`
}

type secret_desc_ui struct {
	Access_key        string `json:"access_key"`
	Secret_key        string `json:"secret_key"`
	Pool              string `json:"owner"`
	Key_policy        string `json:"key_policy"`
	Expiration_time   int64  `json:"expiration_time"`
	Modification_time int64  `json:"modification_time"`
}
