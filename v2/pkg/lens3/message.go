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

	http_500_internal_server_error int = 500
	http_502_bad_gateway           int = 502
	http_503_service_unavailable   int = 503

	http_601_unanalyzable int = 601
)

var message_internal_error = `"(internal-error)"`

// ERROR_MESSAGE is an error message to be returned to the client.
type error_message [2]string

// Error messages returned to clients by Multiplexer.
var (
	message_inconsistent_db = error_message{
		"message", "(internal) Bad keyval-db, inconsistent"}
	message_bad_db_entry = error_message{
		"message", "(internal) Bad keyval-db entry"}

	message_bad_signature = error_message{
		"message", "Bad signature"}
	message_not_authenticated = error_message{
		"message", "Not authenticated"}
	message_not_authorized = error_message{
		"message", "Not authorized"}
	message_unknown_credential__ = error_message{
		"message", "Unknown credential"}
	message_bad_credential__ = error_message{
		"message", "Bad credential"}

	message_backend_not_running = error_message{
		"message", "Backend not running"}
	message_bad_backend_ep = error_message{
		"message", "Bad backend ep"}
	message_cannot_start_backend = error_message{
		"message", "Cannot start backend"}

	message_access_rejected = error_message{
		"message", "Rejected"}
	message_bad_bucket_name = error_message{
		"message", "Bad bucket name"}
	message_no_named_bucket = error_message{
		"message", "No named bucket"}

	message_bucket_expired = error_message{
		"message", "Bucket expired"}

	message_bucket_listing_forbidden = error_message{
		"message", "Bucket listing forbidden"}

	message_nonexisting_pool = error_message{
		"message", "Nonexisting pool"}

	message_no_permission = error_message{
		"message", "No permission"}

	message_user_not_registered = error_message{
		"message", "User not registered"}
	message_user_disabled = error_message{
		"message", "User disabled"}
	message_no_user_account = error_message{
		"message", "No user account"}
	message_user_account_conflict = error_message{
		"message", "User accounts conflict"}

	message_pool_not_ready = error_message{
		"message", "Pool not ready"}
	message_pool_suspended = error_message{
		"message", "Pool suspended"}
	message_pool_disabled = [2]string{
		"message", "Pool disabled"}
	message_pool_inoperable = [2]string{
		"message", "Pool inoperable"}
)

// Error messages returned to clients by Registrar.
var (
	message_Lens3_not_running = error_message{
		"message", "Lens3 is not running"}
	message_Proxy_untrusted = error_message{
		"message", "Proxy_untrusted (bad configuration)"}
	message_Bad_csrf_tokens = error_message{
		"message", "Missing or bad csrf-tokens"}

	message_Arguments_not_empty = error_message{
		"message", "Arguments not empty"}
	message_Bad_body_encoding = error_message{
		"message", "Bad body encoding"}

	message_Bad_user_account = error_message{
		"message", "Missing or bad user account"}
	message_Bad_group = error_message{
		"message", "Bad group"}
	message_No_pool = error_message{
		"message", "No pool"}
	message_Bad_pool_state = error_message{
		"message", "Bad pool state"}

	message_No_bucket = error_message{
		"message", "No bucket"}
	message_No_secret = error_message{
		"message", "No secret"}

	message_Not_bucket_owner = error_message{
		"message", "Not bucket owner"}
	message_Not_secret_owner = error_message{
		"message", "Not secret owner"}

	message_Bad_buckets_directory = error_message{
		"message", "Buckets-directory is not absolute"}
	message_Bad_bucket = error_message{
		"message", "Bad bucket"}
	message_Bad_secret = error_message{
		"message", "Bad secret"}
	message_Bad_policy = error_message{
		"message", "Bad policy"}
	message_Bad_expiration = error_message{
		"message", "Bad expiration"}

	message_Bucket_already_taken = error_message{
		"message", "Bucket already taken"}
	message_Buckets_directory_already_taken = error_message{
		"message", "Buckets directory already taken"}
)
