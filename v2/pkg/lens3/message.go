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

var message_internal_error = `"(internal-error)"`

// ERROR_MESSAGE is an error message to be returned to clients.
type error_message [2]string

// Error messages returned to clients by Multiplexer and Regisrar.
var (
	message_500_bad_db_entry = error_message{
		"message", "(internal) Bad keyval-db entry"}

	message_503_pool_suspended = error_message{
		"message", "Pool suspended"}
)

// Error messages returned to clients by Multiplexer.
var (
	message_400_bad_bucket_name = error_message{
		"message", "Bad bucket name"}
	message_400_bucket_listing_forbidden = error_message{
		"message", "Bucket listing forbidden"}

	message_403_bucket_expired = error_message{
		"message", "Bucket expired"}
	message_403_not_authorized = error_message{
		"message", "Not authorized"}
	message_403_no_permission = error_message{
		"message", "No permission"}
	message_403_user_not_registered = error_message{
		"message", "User not registered"}
	message_403_user_disabled = error_message{
		"message", "User disabled"}
	message_403_no_user_account = error_message{
		"message", "No user account"}
	message_403_pool_disabled = [2]string{
		"message", "Pool disabled"}

	message_404_nonexisting_pool = error_message{
		"message", "Nonexisting pool"}
	message_404_no_named_bucket = error_message{
		"message", "No named bucket"}

	message_500_bad_backend_ep = error_message{
		"message", "Bad backend ep"}
	message_500_cannot_start_backend = error_message{
		"message", "Cannot start backend"}
	message_500_sign_failed = error_message{
		"message", "Signing by aws.signer failed"}
	message_500_user_account_conflict = error_message{
		"message", "User accounts conflict"}

	message_500_pool_inoperable = [2]string{
		"message", "Pool inoperable"}

	message_pool_not_ready__ = error_message{
		"message", "Pool not ready"}
	message_backend_not_running__ = error_message{
		"message", "Backend not running"}

	message_401_access_rejected = error_message{
		"message", "Rejected"}
	message_403_access_rejected = error_message{
		"message", "Rejected"}
	message_500_access_rejected = error_message{
		"message", "Rejected"}
)

// Error messages returned to clients by Registrar.
var (
	message_400_arguments_not_empty = error_message{
		"message", "Arguments not empty"}
	message_400_bad_body_encoding = error_message{
		"message", "Bad body encoding"}
	message_400_bad_group = error_message{
		"message", "Bad group"}
	message_400_bad_bucket_directory = error_message{
		"message", "Bucket-directory is not absolute"}
	message_400_bad_bucket = error_message{
		"message", "Bad bucket"}
	message_400_bad_policy = error_message{
		"message", "Bad policy"}
	message_400_bad_expiration = error_message{
		"message", "Bad expiration"}

	message_401_bad_user_account = error_message{
		"message", "Missing or bad user account"}
	message_401_bad_csrf_tokens = error_message{
		"message", "Missing or bad csrf-tokens"}

	message_403_not_bucket_owner = error_message{
		"message", "Not bucket owner"}
	message_403_not_secret_owner = error_message{
		"message", "Not secret owner"}

	message_404_no_bucket = error_message{
		"message", "No bucket"}
	message_404_no_secret = error_message{
		"message", "No secret"}

	message_409_bucket_already_taken = error_message{
		"message", "Bucket already taken"}
	message_409_bucket_directory_already_taken = error_message{
		"message", "Bucket-directory already taken"}

	message_500_inconsistent_db = error_message{
		"message", "(internal) Bad keyval-db, inconsistent"}

	message_500_lens3_not_running = error_message{
		"message", "Lens3 is not running"}
	message_500_proxy_untrusted = error_message{
		"message", "Proxy_untrusted (bad configuration)"}

	message_400_no_pool = error_message{
		"message", "No pool"}
	message_403_no_pool = error_message{
		"message", "No pool"}
	message_404_no_pool = error_message{
		"message", "No pool"}

	message_403_bad_pool_state = error_message{
		"message", "Bad pool state"}
	message_500_bad_pool_state = error_message{
		"message", "Bad pool state"}

	message_400_bad_secret = error_message{
		"message", "Bad secret"}
	message_404_bad_secret = error_message{
		"message", "Bad secret"}
)
