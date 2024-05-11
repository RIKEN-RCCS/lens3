/* AWS S3 Signer. */

// Copyright 2022-2024 RIKEN R-CCS
// SPDX-License-Identifier: BSD-2-Clause

package lens3

// Some reference documents:
//   https://docs.aws.amazon.com/AmazonS3/latest/API/sig-v4-header-based-auth.html
//   https://docs.aws.amazon.com/AmazonS3/latest/API/sigv4-auth-using-authorization-header.html
//   https://docs.aws.amazon.com/AmazonS3/latest/API/RESTCommonRequestHeaders.html

import (
	"fmt"
	//"flag"
	"context"
	//"io"
	//"log"
	//"os"
	//"net"
	"maps"
	"net/http"
	//"net/http/httputil"
	//"net/url"
	"regexp"
	"slices"
	"strings"
	"time"
	//"runtime"
	"github.com/aws/aws-sdk-go-v2/aws"
	signer "github.com/aws/aws-sdk-go-v2/aws/signer/v4"
)

// S3V4_AUTHORIZATION is Authorization header entries.
type s3v4_authorization struct {
	credential    [5]string
	signedheaders []string
	signature     string
}

// REQUIRED_HEADERS is a list that are checked their existence in
// Authorization.Signedheaders.  They are canonicalized although they
// appear in lowercase in Authorization.Signedheaders.  Other required
// headers are (in the chunked case): "Content-Encoding",
// "X-Amz-Decoded-Content-Length", "Content-Length".  Additionally,
// AWS-CLI also sends "Content-Md5".
var required_headers = [3]string{
	"Host", "X-Amz-Content-Sha256", "X-Amz-Date",
}

const s3v4_authorization_method = "AWS4-HMAC-SHA256"

// CHECK_CREDENTIAL_IN_REQUEST checks the sign in an http request.  It
// once signs a request using AWS SDK, and compares results.
func check_credential_in_request(verbose bool, q *http.Request, keypair [2]string) bool {
	var auth1 = q.Header.Get("Authorization")
	if auth1 == "" {
		//fmt.Println("*** empty authorization=", auth1)
		return false
	}
	var auth_passed s3v4_authorization = scan_aws_authorization(auth1)
	if auth_passed.signature == "" {
		//fmt.Println("*** bad auth=", auth1)
		return false
	}

	var service = auth_passed.credential[3]
	var region = auth_passed.credential[2]
	var datestring = fix_x_amz_date(q.Header.Get("X-Amz-Date"))
	var date, errx = time.Parse(time.RFC3339, datestring)
	if errx != nil {
		//fmt.Println("*** bad date=", auth_passed)
		return false
	}

	var r = *q
	r.Header = maps.Clone(q.Header)

	// Filter out except the specified headers for signing.

	maps.DeleteFunc(r.Header, func(k string, v []string) bool {
		return slices.Index(auth_passed.signedheaders, k) == -1
	})
	if slices.Index(auth_passed.signedheaders, "Content-Length") == -1 {
		r.ContentLength = -1
	}
	fmt.Println("*** r.Host=", r.Host)

	var credentials = aws.Credentials{
		AccessKeyID:     keypair[0],
		SecretAccessKey: keypair[1],
		//SessionToken string
		//Source string
		//CanExpire bool
		//Expires time.Time
	}
	var hash = r.Header.Get("X-Amz-Content-Sha256")
	//fmt.Println("*** X-Amz-Content-Sha256=", hash)
	if hash == "" {
		// It is a bad idea to use a hash for an empty payload.
		hash = empty_payload_hash_sha256
	}
	var s = signer.NewSigner(func(s *signer.SignerOptions) {
		// No options.
	})
	var timeout = time.Duration(10 * time.Second)
	var ctx, cancel = context.WithTimeout(context.Background(), timeout)
	defer cancel()
	var err1 = s.SignHTTP(ctx, credentials, &r,
		hash, service, region, date)
	if err1 != nil {
		fmt.Println("Signer.SignHTTP()", err1)
	}

	var auth2 = r.Header.Get("Authorization")
	var auth_forged s3v4_authorization = scan_aws_authorization(auth2)

	if verbose && auth_passed.signature != auth_forged.signature {
		logger.debugf("Mux() Bad signature"+
			" passed-request=%v forged-request=%v", q, r)
	}

	return auth_passed.signature == auth_forged.signature
}

// SIGN_BY_BACKEND_CREDENTIAL replaces an authorization header in an
// http request for the backend.
func sign_by_backend_credential(r *http.Request, proc Process_record) {
	if false {
		fmt.Println("r.Host(1)=", r.Host)
		fmt.Println("r.Header(1)=", r.Header)
		var a1 = r.Header.Get("Authorization")
		fmt.Println("Authorization(1)=", a1)
		var a2 = r.Header.Get("x-amz-content-sha256")
		fmt.Println("x-amz-content-sha256(1)=", a2)
	}

	fmt.Println("*** proc.Backend_ep=", proc.Backend_ep)

	//r.Header.Del("Accept-Encoding")
	r.Host = proc.Backend_ep
	var credentials = aws.Credentials{
		AccessKeyID:     proc.Root_access,
		SecretAccessKey: proc.Root_secret,
		//SessionToken string
		//Source string
		//CanExpire bool
		//Expires time.Time
	}
	var hash = r.Header.Get("X-Amz-Content-Sha256")
	if hash == "" {
		// It is a bad idea to use a hash for an empty payload.
		hash = empty_payload_hash_sha256
	}
	var service = "s3"
	var region = "us-east-1"
	var date = time.Now()
	var s = signer.NewSigner(func(s *signer.SignerOptions) {
		// No options.
	})
	var timeout = time.Duration(10 * time.Second)
	var ctx, cancel = context.WithTimeout(context.Background(), timeout)
	defer cancel()
	var err1 = s.SignHTTP(ctx, credentials, r,
		hash, service, region, date)
	assert_fatal(err1 == nil)

	if false {
		fmt.Println("date(2)=", date)
		fmt.Println("r.Host(2)=", r.Host)
		fmt.Println("r.Header(2)=", r.Header)
		var a3 = r.Header.Get("Authorization")
		fmt.Println("Authorization(2)=", a3)
		var a4 = r.Header.Get("x-amz-content-sha256")
		fmt.Println("x-amz-content-sha256(2)=", a4)
	}
}

// SCAN_AWS_AUTHORIZATION extracts elements in an "Authorization"
// header.  On failure, it returns one with the signature field as "".
// Keys in SignedHeaders are stored canonicalized.  An authorization
// header starts with a keyword "AWS4-HMAC-SHA256", and consists of
// three fields separated by "," and zero or more blanks.  A
// credential is a five fields separated by "/" as
// KEY/DATE/REGION/SERVICE/TYPE_OF_USAGE, with DATE="yyyymmdd",
// SERVICE="s3", and TYPE_OF_USAGE="aws4_request".  A signedheaders is
// a list of header keys separated by ";" as
// "host;x-amz-content-sha256;x-amz-date".  A signature is a string.
//
// Authorization="AWS4-HMAC-SHA256
//
//	Credential={key}/20240511/us-east-1/s3/aws4_request,
//	SignedHeaders=host;x-amz-content-sha256;x-amz-date,
//	Signature={signature}"
func scan_aws_authorization(auth string) s3v4_authorization {
	var bad = s3v4_authorization{}
	var i1 = strings.Index(auth, " ")
	if i1 == -1 || i1 != 16 {
		//fmt.Println("*** no auth method", auth)
		return bad
	}
	if auth[:16] != s3v4_authorization_method {
		//fmt.Println("*** bad auth method", auth)
		return bad
	}
	var slots [][2]string
	for _, s1 := range strings.Split(auth[16:], ",") {
		var s2 = strings.TrimSpace(s1)
		var i2 = strings.Index(s2, "=")
		if i2 == -1 || i2 == 0 || i2 == (len(s2)-1) {
			continue
		}
		slots = append(slots, [2]string{s2[:i2], s2[i2+1:]})
	}
	if len(slots) != 3 {
		//fmt.Println("*** bad auth entries", auth)
		return bad
	}
	var v = s3v4_authorization{}
	for _, kv := range slots {
		switch kv[0] {
		case "Credential":
			// "Credential={key}/20240511/us-east-1/s3/aws4_request"
			var c1 = strings.Split(kv[1], "/")
			if len(c1) != 5 {
				//fmt.Println("*** bad credential slot", auth)
				return bad
			}
			var c2 = [5]string(c1)
			if !(len(c2[1]) == 8 && check_all_digits(c2[1])) {
				//fmt.Println("*** bad credential-date slot", auth)
				return bad
			}
			if c2[3] != "s3" {
				//fmt.Println("*** bad credential-service slot", auth)
				return bad
			}
			if c2[4] != "aws4_request" {
				//fmt.Println("*** bad credential-usage slot", auth)
				return bad
			}
			v.credential = c2
		case "SignedHeaders":
			// SignedHeaders=host;x-amz-content-sha256;x-amz-date
			var headers []string
			for _, h1 := range strings.Split(kv[1], ";") {
				headers = append(headers, http.CanonicalHeaderKey(h1))
			}
			for _, h2 := range required_headers {
				if slices.Index(headers, h2) == -1 {
					//fmt.Println("*** bad signedheaders", h2, headers)
					return bad
				}
			}
			v.signedheaders = headers
		case "Signature":
			v.signature = kv[1]
		default:
			//fmt.Println("*** bad entry", kv)
			return bad
		}
	}
	if v.credential == [5]string{} ||
		v.signedheaders == nil ||
		v.signature == "" {
		//fmt.Println("*** bad missing slots", auth)
		return bad
	}
	return v
}

func check_all_digits(s string) bool {
	var re = regexp.MustCompile(`^[0-9]+$`)
	return re.MatchString(s)
}

// Converts an X-Amz-Date string to one parsable in RFC3339.  It
// returns "" if a string is ill formed.  The date looks like
// "X-Amz-Date=20240509T081007Z".  (X-Amz-Date is an acceptable string
// by ISO-8601).
func fix_x_amz_date(d string) string {
	if len(d) != 16 {
		return ""
	}
	return (d[0:4] + "-" +
		d[4:6] + "-" +
		d[6:11] + ":" +
		d[11:13] + ":" +
		d[13:])
}
