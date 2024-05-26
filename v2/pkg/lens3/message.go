/* Lens3 Messages Returned to Clients. */

// Copyright 2022-2024 RIKEN R-CCS.
// SPDX-License-Identifier: BSD-2-Clause

package lens3

var (
	message_backend_not_running = [2]string{
		"message", "Backend not running"}
	message_bad_backend_ep = [2]string{
		"message", "Bad backend ep"}
	message_cannot_start_backend = [2]string{
		"message", "Cannot start backend"}

	message_bad_signature = [2]string{
		"message", "Bad signature"}
	message_not_authenticated = [2]string{
		"message", "Not authenticated"}
	message_not_authorized = [2]string{
		"message", "Not authorized"}

	message_no_bucket_name = [2]string{
		"message", "No bucket name"}
	message_bad_bucket_name = [2]string{
		"message", "Bad bucket name"}
	message_no_named_bucket = [2]string{
		"message", "No named bucket"}

	message_bucket_expired = [2]string{
		"message", "Bucket expired"}

	message_bucket_listing_forbidden = [2]string{
		"message", "Bucket listing forbidden"}

	message_bad_pool = [2]string{
		"message", "Bad pool"}
	message_nonexisting_pool = [2]string{
		"message", "Nonexisting pool"}

	message_no_permission = [2]string{
		"message", "No permission"}
)

var (
	message_internal_error = [][2]string{{"message", "(internal)"}}
)

var (
	message_Lens3_not_running = [2]string{
		"message", "Lens3 is not running"}
	message_Bad_proxy_configuration = [2]string{
		"message", "Bad proxy configuration"}
	message_Bad_user_account = [2]string{
		"message", "Missing or bad user_account"}
	message_Bad_csrf_tokens = [2]string{
		"message", "Missing or bad csrf-tokens"}
	message_No_pool = [2]string{
		"message", "No pool"}
	message_No_bucket = [2]string{
		"message", "No bucket"}
	message_No_secret = [2]string{
		"message", "No secret"}
	message_Not_pool_owner = [2]string{
		"message", "Not pool owner"}
	message_Not_bucket_owner = [2]string{
		"message", "Not bucket owner"}
	message_Not_secret_owner = [2]string{
		"message", "Not secret owner"}
	message_Arguments_not_empty = [2]string{
		"message", "Arguments not empty"}
	message_Bad_body_encoding = [2]string{
		"message", "Bad body encoding"}
	message_Bad_group = [2]string{
		"message", "Bad group"}
	message_Bad_pool = [2]string{
		"message", "Bad pool"}
	message_Bad_buckets_directory = [2]string{
		"message", "Buckets-directory is not absolute"}
	message_Bad_bucket = [2]string{
		"message", "Bad bucket"}
	message_Bad_secret = [2]string{
		"message", "Bad secret"}
	message_Bad_policy = [2]string{
		"message", "Bad policy"}
	message_Bad_expiration = [2]string{
		"message", "Bad expiration"}
	message_Bucket_already_taken = [2]string{
		"message", "Bucket already taken"}
	message_Buckets_directory_already_taken = [2]string{
		"message", "Buckets directory already taken"}
)
