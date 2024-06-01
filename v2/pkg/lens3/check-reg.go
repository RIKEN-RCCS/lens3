/* Check Reg. */

package lens3

import (
	//"bufio"
	"bytes"
	//"context"
	"encoding/json"
	"fmt"
	//"log"
	"net/http"
	"time"
	//"reflect"
	"io"
	"os"
	//"os/exec"
	//"os/signal"
	"os/user"
	//"strings"
	//"syscall"
	//"testing"
)

func run_registrar(n int) {
	var dbconf = read_db_conf("conf.json")
	var t = make_table(dbconf)
	var muxconf = get_mux_conf(t, "mux")
	var regconf = get_reg_conf(t, "reg")
	_ = muxconf

	var z = &the_registrar
	configure_registrar(z, t, nil, regconf)

	fmt.Println("now+365=", time.Now().AddDate(0, 0, 30).Unix())

	clear_everything(z.table)

	go start_registrar(z)

	time.Sleep(1 * time.Second)

	switch n {
	case 1:
		run_dummy_reg_client()
	case 2:
		run_dummy_reg_client_leaving_pool()
	default:
		run_dummy_reg_client()
	}
}

type reg_customer struct {
	client     *http.Client
	ep         string
	uid        string
	user       *user.User
	group      *user.Group
	csrf_token string
	pool       string
	buckets    []string
	secrets    []string
	response   any
	verbose    bool
}

func run_dummy_reg_client() {
	fmt.Println("reg client run...")

	var user1, err1 = user.Current()
	if err1 != nil {
		panic(err1)
	}

	var group1, err2 = user.LookupGroupId(user1.Gid)
	if err2 != nil {
		panic(err2)
	}

	var client = &http.Client{}

	var c = &reg_customer{
		client:     client,
		ep:         "http://localhost:8004/",
		uid:        user1.Username,
		user:       user1,
		group:      group1,
		csrf_token: "",
		pool:       "",
		buckets:    []string{},
		verbose:    true,
	}

	get_user_info(c, 200)
	make_pool(c, "pool-x", 200)
	make_pool(c, "pool-x", 400)
	list_pool(c, 200)
	make_bucket(c, "lenticularis-oddity-x3", 200)
	make_bucket(c, "lenticularis-oddity-x3", 400)
	make_secret(c, 200)
	make_secret(c, 200)
	list_pool(c, 200)
	delete_bucket(c, "lenticularis-oddity-x3", 200)
	delete_secret(c, c.secrets[0], 200)
	delete_secret(c, c.secrets[1], 200)
	remove_pool(c, 200)
}

func run_dummy_reg_client_leaving_pool() {
	fmt.Println("reg client run...")

	var user1, err1 = user.Current()
	if err1 != nil {
		panic(err1)
	}

	var group1, err2 = user.LookupGroupId(user1.Gid)
	if err2 != nil {
		panic(err2)
	}

	var client = &http.Client{}

	var c = &reg_customer{
		client:     client,
		ep:         "http://localhost:8004/",
		uid:        user1.Username,
		user:       user1,
		group:      group1,
		csrf_token: "",
		pool:       "",
		buckets:    []string{},
		verbose:    false,
	}

	get_user_info(c, 200)
	make_pool(c, "pool-x", 200)
	make_bucket(c, "lenticularis-oddity-x3", 200)
	make_secret(c, 200)
	list_pool(c, 200)
}

func consume_response(c *reg_customer, opr string, rsp *http.Response) {
	if c.verbose {
		fmt.Println(opr, "client.Do() response=", rsp)
	}
	var content, err1 = io.ReadAll(rsp.Body)
	if err1 != nil {
		panic(err1)
	}
	if c.verbose {
		fmt.Println(opr, "client.Do() content=", string(content))
	}

	var data any
	var err2 = json.Unmarshal(content, &data)
	if err2 != nil {
		panic(err2)
	}
	c.response = data
	if rsp.StatusCode != 200 {
		var msg = get_string_in_string_map(c.response, "reason", "message")
		fmt.Println("error=", msg)
	}
}

func check_expected_code(c *reg_customer, opr string, rsp *http.Response, code int) {
	if rsp.StatusCode != code {
		fmt.Println("client.Do() BAD, returned=", rsp.StatusCode,
			"expected=", code)
		os.Exit(1)
	}
}

func get_string_in_string_map(v1 any, keys ...string) string {
	var vv = get_any_in_string_map(v1, keys...)
	var v3, ok3 = vv.(string)
	if !ok3 {
		panic("v.(string)")
	}
	return v3
}

func get_any_in_string_map(v1 any, keys ...string) any {
	var vv = v1
	for _, key := range keys {
		var m1, ok1 = vv.(map[string]any)
		if !ok1 {
			panic("v.(map[string]any)")
		}
		var v2, ok2 = m1[key]
		if !ok2 {
			panic("v[key]")
		}
		//fmt.Println("map", vv, "→", v2)
		vv = v2
	}
	return vv
}

func get_user_info(c *reg_customer, code int) {
	//client *http.Client, user1 *user.User, group1 *user.Group
	var opr = "get_user_info"
	fmt.Println("")
	fmt.Println("")

	var url1 = c.ep + "user-info"
	var req, err2 = http.NewRequest("GET", url1, nil)
	if err2 != nil {
		panic(err2)
	}
	//req.Header.Add("X-Real-Ip", "localhost")
	req.Header.Add("X-Remote-User", c.uid)
	var rsp, err3 = c.client.Do(req)
	if err3 != nil {
		panic(err3)
	}

	consume_response(c, opr, rsp)
	check_expected_code(c, opr, rsp, code)

	if rsp.StatusCode == 200 {
		fmt.Println(opr, "client.Do() content=", c.response)

		var v1 = get_string_in_string_map(c.response, "x_csrf_token")
		fmt.Println("csrf_token=", v1)
		c.csrf_token = v1
	}
}

func make_pool(c *reg_customer, dir string, code int) {
	//client *http.Client, user1 *user.User, group1 *user.Group,
	var opr = "make_pool"
	fmt.Println("")
	fmt.Println("")
	var args1 = make_pool_arguments{
		Buckets_directory: (c.user.HomeDir + "/" + dir),
		Owner_gid:         c.group.Name,
	}
	var b1, err1 = json.Marshal(args1)
	if err1 != nil {
		panic(err1)
	}
	var body1 = bytes.NewReader(b1)

	var url1 = c.ep + "pool"
	var req, err2 = http.NewRequest("POST", url1, body1)
	if err2 != nil {
		panic(err2)
	}
	//req.Header.Add("X-Real-Ip", "localhost")
	req.Header.Add("X-Remote-User", c.uid)
	req.Header.Add("X-Csrf-Token", c.csrf_token)
	var rsp, err3 = c.client.Do(req)
	if err3 != nil {
		panic(err3)
	}

	consume_response(c, opr, rsp)
	check_expected_code(c, opr, rsp, code)

	if rsp.StatusCode == 200 {
		var v1 = get_string_in_string_map(c.response, "pool_desc", "pool_name")
		fmt.Println("pool=", v1)
		c.pool = v1
	}
}

func remove_pool(c *reg_customer, code int) {
	var opr = "delete_pool"
	fmt.Println("")
	fmt.Println("")
	var body1 io.Reader = nil
	var url1 = c.ep + "pool/" + c.pool
	var req, err2 = http.NewRequest("DELETE", url1, body1)
	if err2 != nil {
		panic(err2)
	}
	//req.Header.Add("X-Real-Ip", "localhost")
	req.Header.Add("X-Remote-User", c.uid)
	req.Header.Add("X-Csrf-Token", c.csrf_token)
	var rsp, err3 = c.client.Do(req)
	if err3 != nil {
		panic(err3)
	}

	consume_response(c, opr, rsp)
	check_expected_code(c, opr, rsp, code)

	if rsp.StatusCode == 200 {
		fmt.Println(opr, "client.Do() content=", c.response)
	}
}

func list_pool(c *reg_customer, code int) {
	//client *http.Client, user1 *user.User, group1 *user.Group
	var opr = "list_pool"
	fmt.Println("")
	fmt.Println("")
	var url1 = c.ep + "pool"
	var req, err2 = http.NewRequest("GET", url1, nil)
	if err2 != nil {
		panic(err2)
	}
	//req.Header.Add("X-Real-Ip", "localhost")
	req.Header.Add("X-Remote-User", c.uid)
	req.Header.Add("X-Csrf-Token", c.csrf_token)
	var rsp, err3 = c.client.Do(req)
	if err3 != nil {
		panic(err3)
	}

	consume_response(c, opr, rsp)
	check_expected_code(c, opr, rsp, code)

	if rsp.StatusCode == 200 {
		fmt.Println(opr, "client.Do() content=", c.response)
	}
}

func make_bucket(c *reg_customer, bucket string, code int) {
	//client *http.Client, user1 *user.User, group1 *user.Group
	var opr = "make_bucket"
	fmt.Println("")
	fmt.Println("")
	var args1 = &make_bucket_arguments{
		Bucket:        bucket,
		Bucket_policy: "public",
	}
	var b1, err1 = json.Marshal(args1)
	if err1 != nil {
		panic(err1)
	}
	var body1 = bytes.NewReader(b1)

	var url1 = c.ep + "pool/" + c.pool + "/bucket"
	var req, err2 = http.NewRequest("PUT", url1, body1)
	if err2 != nil {
		panic(err2)
	}
	//req.Header.Add("X-Real-Ip", "localhost")
	req.Header.Add("X-Remote-User", c.uid)
	req.Header.Add("X-Csrf-Token", c.csrf_token)
	var rsp, err3 = c.client.Do(req)
	if err3 != nil {
		panic(err3)
	}

	consume_response(c, opr, rsp)
	check_expected_code(c, opr, rsp, code)

	if rsp.StatusCode == 200 {
		fmt.Println(opr, "client.Do() content=", c.response)
	}
}

func delete_bucket(c *reg_customer, bucket string, code int) {
	//client *http.Client, user *user.User, group1 *user.Group
	var opr = "delete_bucket"
	fmt.Println("")
	fmt.Println("")
	var body1 io.Reader = nil
	var url1 = c.ep + "pool/" + c.pool + "/bucket/" + bucket
	var req, err2 = http.NewRequest("DELETE", url1, body1)
	if err2 != nil {
		panic(err2)
	}
	//req.Header.Add("X-Real-Ip", "localhost")
	req.Header.Add("X-Remote-User", c.uid)
	req.Header.Add("X-Csrf-Token", c.csrf_token)
	var rsp, err3 = c.client.Do(req)
	if err3 != nil {
		panic(err3)
	}

	consume_response(c, opr, rsp)
	check_expected_code(c, opr, rsp, code)

	if rsp.StatusCode == 200 {
		fmt.Println(opr, "client.Do() content=", c.response)
	}
}

func make_secret(c *reg_customer, code int) {
	var opr = "make_secret"
	fmt.Println("")
	fmt.Println("")
	var args1 = &make_secret_arguments{
		Secret_policy:   "readwrite",
		Expiration_time: time.Now().AddDate(0, 0, 30).Unix(),
	}
	var b1, err1 = json.Marshal(args1)
	if err1 != nil {
		panic(err1)
	}
	var body1 = bytes.NewReader(b1)

	var url1 = c.ep + "pool/" + c.pool + "/secret"
	var req, err2 = http.NewRequest("POST", url1, body1)
	if err2 != nil {
		panic(err2)
	}
	//req.Header.Add("X-Real-Ip", "localhost")
	req.Header.Add("X-Remote-User", c.uid)
	req.Header.Add("X-Csrf-Token", c.csrf_token)
	var rsp, err3 = c.client.Do(req)
	if err3 != nil {
		panic(err3)
	}

	consume_response(c, opr, rsp)
	check_expected_code(c, opr, rsp, code)

	if rsp.StatusCode == 200 {
		var vv = get_any_in_string_map(c.response, "pool_desc", "secrets")
		var v1, ok1 = vv.([]any)
		if !ok1 {
			panic("v.([]any)")
		}
		var accesskeys []string
		for _, accesskey := range v1 {
			var k = get_string_in_string_map(accesskey, "access_key")
			accesskeys = append(accesskeys, k)
		}
		c.secrets = accesskeys
		fmt.Println("secrets=", c.secrets)
	}
}

func delete_secret(c *reg_customer, secret string, code int) {
	var opr = "delete_secret"
	fmt.Println("")
	fmt.Println("")
	var body1 io.Reader = nil
	var url1 = c.ep + "pool/" + c.pool + "/secret/" + secret
	var req, err2 = http.NewRequest("DELETE", url1, body1)
	if err2 != nil {
		panic(err2)
	}
	//req.Header.Add("X-Real-Ip", "localhost")
	req.Header.Add("X-Remote-User", c.uid)
	req.Header.Add("X-Csrf-Token", c.csrf_token)
	var rsp, err3 = c.client.Do(req)
	if err3 != nil {
		panic(err3)
	}

	consume_response(c, opr, rsp)
	check_expected_code(c, opr, rsp, code)

	if rsp.StatusCode == 200 {
		fmt.Println(opr, "client.Do() content=", c.response)
	}
}