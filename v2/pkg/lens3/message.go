/* Lens3 Messages Returned to Clients. */

// Copyright 2022-2024 RIKEN R-CCS.
// SPDX-License-Identifier: BSD-2-Clause

package lens3

const (
	http_200_OK int = 200

	http_400_bad_request  int = 400
	http_401_unauthorized int = 401
	http_403_forbidden    int = 403
	http_404_not_found    int = 404
	http_409_conflict     int = 409

	http_500_internal_server_error int = 500
	http_502_bad_gateway           int = 502
	http_503_service_unavailable   int = 503

	http_601_too_much_data int = 601
)

// ERROR_MESSAGE is an error message to be returned to clients.
type error_message [2]string

// Error messages returned to clients by Multiplexer and Regisrar.
var (
	message_500_bad_db_entry = "(internal) Bad keyval-db entry"

	message_502_bucket_creation_failed = "Bucket creation failed"
	message_503_pool_suspended         = "Pool suspended"
)

// Error messages returned to clients by Multiplexer.
var (
	message_40x_access_rejected          = "Rejected"
	message_400_bucket_listing_forbidden = "Bucket listing forbidden"

	message_403_bucket_expired      = "Bucket expired"
	message_403_not_authorized      = "Not authorized"
	message_403_no_permission       = "No permission"
	message_403_user_not_registered = "User not registered"
	message_403_user_disabled       = "User disabled"
	message_403_no_user_account     = "No user account"
	message_403_pool_disabled       = "Pool disabled"

	message_404_nonexisting_pool = "Nonexisting pool"
	message_404_no_named_bucket  = "No named bucket"

	message_50x_internal_error        = "(internal-error)"
	message_500_access_rejected       = "Rejected"
	message_500_pool_inoperable       = "Pool inoperable"
	message_500_sign_failed           = "Signing by aws.signer failed"
	message_500_cannot_start_backend  = "Cannot start backend"
	message_500_user_account_conflict = "User accounts conflict"
	message_503_proxying_failed       = "Proxying failed"
)

// Error messages returned to clients by Registrar.
var (
	message_400_arguments_not_empty  = "Arguments not empty"
	message_400_bad_body_encoding    = "Bad body encoding"
	message_400_bad_group            = "Bad group"
	message_400_bad_bucket_directory = "Bucket-directory is not absolute"
	message_400_bad_bucket           = "Bad bucket"
	message_400_bad_policy           = "Bad policy"
	message_400_bad_expiration       = "Bad expiration"

	message_401_bad_user_account = "Missing or bad user account"
	message_401_bad_csrf_tokens  = "Missing or bad csrf-tokens"

	message_403_not_bucket_owner = "Not bucket owner"
	message_403_not_secret_owner = "Not secret owner"

	message_404_no_bucket = "No bucket"
	message_404_no_secret = "No secret"

	message_409_bucket_already_taken           = "Bucket already taken"
	message_409_bucket_directory_already_taken = "Bucket-directory already taken"

	message_500_inconsistent_db = "(internal) Bad keyval-db, inconsistent"

	message_500_lens3_not_running = "Lens3 is not running"
	message_500_proxy_untrusted   = "Proxy_untrusted (bad configuration)"

	message_400_no_pool = "No pool"
	message_403_no_pool = "No pool"
	message_404_no_pool = "No pool"

	message_403_bad_pool_state = "Bad pool state"
	message_500_bad_pool_state = "Bad pool state"

	message_400_bad_secret = "Bad secret"
	message_404_bad_secret = "Bad secret"
)
