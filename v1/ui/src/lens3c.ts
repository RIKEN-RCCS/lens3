/* Lens3 Client */

/* Copyright (c) 2022-2023 RIKEN R-CCS */
/* SPDX-License-Identifier: BSD-2-Clause */

import {reactive, computed} from "vue";

let csrf_token : string;
const base_path : string = Function("return base_path_")();

/* Editor State. */

const pool_data_ = {
  /* Entries for PoolMake. */

  buckets_directory: "",
  user: "",
  group: "",
  group_choices: [],

  /* Entries for PoolList. */

  pool_list: [],

  /* Entries for PoolEdit. */

  buckets: [],
  access_keys: [],
  probe_key: "",
  expiration_time: "",
  online_status: "",
  user_enabled_status: "",
  minio_state: "",
  minio_reason: "",
  modification_time: "",

  access_key_set: {},
  access_keys_rw: [],
  access_keys_ro: [],
  access_keys_wo: [],

  pool_name: "",
  bucket_name: "",
  bucket_policy: "",
  key_expiration_time: "",

  edit_pool_visible: false,
  //pool_name_visible: true,
  //pool_args_visible: false,
  //make_pool_mode: false,

  dialog: "hello",
  show_dialog: false,

  edit_pool(i : number) {
    const d = this.pool_list[i]
    const data = {"pool_desc": d};
    set_pool_data(data);
  },

  api_get_user_info() {
    const method = "GET";
    const path = (base_path + "/user-info");
    const body = null;
    const triple = {method, path, body};
    submit_request("get_user_info", triple, set_user_info_data);
  },

  api_list_pools() {
    const method = "GET";
    const path = (base_path + "/pool");
    const body = null;
    const triple = {method, path, body};
    return submit_request("list_pools", triple, set_pool_list);
  },

  api_make_pool() {
    console.log("make_pool: this=" + this);
    const directory = this.buckets_directory;
    const gid = this.group;
    console.log("make_pool: directory=" + directory + ", group=" + gid);
    const method = "POST";
    const path = (base_path + "/pool");
    const args = {"buckets_directory": directory,
                  "owner_gid": gid,
                  "CSRF-Token": csrf_token};
    const body = JSON.stringify(args);
    const triple = {method, path, body};
    return submit_request("make_pool", triple, 
                          (data) => {this.api_list_pools();});
  },

  api_delete_pool(pool : string) {
    console.log("delete_pool: id=" + pool);
    const method = "DELETE";
    const path = (base_path + "/pool/" + pool);
    const args = {"CSRF-Token": csrf_token};
    const body = JSON.stringify(args);
    const triple = {method, path, body};
    return submit_request("delete_pool", triple,
                          (data) => {this.api_list_pools();});
  },

  api_make_bucket(pool : string, name : string, policy : string) {
    console.log("make_bucket: name=" + name + ", policy=" + policy);
    const method = "PUT";
    const path = (base_path + "/pool/" + pool + "/bucket");
    const args = {"name": name,
                  "bkt_policy": policy,
                  "CSRF-Token": csrf_token};
    const body = JSON.stringify(args);
    const triple = {method, path, body};
    return submit_request("make_bucket", triple, set_pool_data);
  },

  api_delete_bucket(pool : string, name : string) {
    const msg = "delete_bucket";
    console.log("delete_bucket: name=" + name);
    const method = "DELETE";
    const path = (base_path + "/pool/" + pool_data.pool_name
                  + "/bucket/" + name);
    const args = {"CSRF-Token": csrf_token};
    const body = JSON.stringify(args);
    const triple = {method, path, body};
    return submit_request(msg, triple, set_pool_data);
  },

  api_make_secret(pool : string, rw : string) {
    console.log("make_secret: " + rw);
    const expiration = parse_time_z(pool_data.key_expiration_time);
    const method = "POST";
    const path = (base_path + "/pool/" + pool_data.pool_name
                  + "/secret");
    const args = {"key_policy": rw,
                  "expiration_time": expiration,
                  "CSRF-Token": csrf_token};
    const body = JSON.stringify(args);
    const triple = {method, path, body};
    return submit_request("make_secret", triple, set_pool_data);
  },

  api_delete_secret(pool : string, key : string) {
    const msg = "delete_secret";
    console.log("delete_secret: " + key);
    const method = "DELETE";
    const path = (base_path + "/pool/" + pool_data.pool_name
                  + "/secret/" + key);
    const args = {"CSRF-Token": csrf_token};
    const body = JSON.stringify(args);
    const triple = {method, path, body};
    return submit_request(msg, triple, set_pool_data);
  },

};

export const pool_data = reactive(pool_data_);

function set_user_info_data(data : any) {
  console.assert(data && data["user_info"]);
  const d = data["user_info"];
  console.assert(d["api_version"] == "v1.2", "Lens3 api mismatch");
  pool_data.user = d["uid"];
  pool_data.group = d["groups"][0];
  pool_data.group_choices = d["groups"];

  pool_data.edit_pool_visible = false;
}

function set_pool_list(data : any) {
  console.assert(data && data["pool_list"]);
  const dd = data["pool_list"]
  console.log("pool_list=" + dd.length);
  console.log(dd);
  for (let i in dd) {
    console.log("pool=" + i);
    console.log(dd[i]);
  }
  pool_data.pool_list = dd;
  pool_data.edit_pool_visible = false;
}

function set_pool_data(data : any) {
  console.assert(data && data["pool_desc"]);
  const d = data["pool_desc"]
  pool_data.pool_name = d["pool_name"];
  pool_data.buckets_directory = d["buckets_directory"];
  pool_data.user = d["owner_uid"];
  pool_data.group = d["owner_gid"];

  pool_data.buckets = d["buckets"];
  pool_data.access_keys = d["access_keys"];
  pool_data.probe_key = d["probe_key"];
  pool_data.expiration_time = d["expiration_time"];
  pool_data.online_status = d["online_status"];
  pool_data.user_enabled_status = d["user_enabled_status"];
  pool_data.minio_state = d["minio_state"];
  pool_data.minio_reason = d["minio_reason"];
  pool_data.modification_time = d["modification_time"];

  const keys = d["access_keys"];
  const rwkeys = keys.filter((k : any) => k["key_policy"] == "readwrite");
  const rokeys = keys.filter((k : any) => k["key_policy"] == "readonly");
  const wokeys = keys.filter((k : any) => k["key_policy"] == "writeonly");
  pool_data.access_keys_rw = format_time_in_keys(rwkeys);
  pool_data.access_keys_ro = format_time_in_keys(rokeys);
  pool_data.access_keys_wo = format_time_in_keys(wokeys);
  pool_data.access_key_set = [
    {policy: "readwrite", keys: pool_data.access_keys_rw},
    {policy: "readonly", keys: pool_data.access_keys_ro},
    {policy: "writeonly", keys: pool_data.access_keys_wo},
  ];

  pool_data.bucket_name = "";
  pool_data.bucket_policy = "none";
  pool_data.edit_pool_visible = true;
}

function format_time_in_keys(keys : any) {
  return keys.map((k : any) => {
    return {"access_key": k["access_key"],
            "secret_key": k["secret_key"],
            "expiration_time": format_time_z(k["expiration_time"])};
  });
}

function parse_time_z(s : string) {
  return (new Date(s).getTime() / 1000);
}

function format_time_z(d : number) {
  /* Returns a date string. */
  /* Returns a date+time string with milliseconds. */
  if (d == 0) {
    return 0;
  } else {
    return new Date(d * 1000).toISOString().substring(0, 10);
  }
}

function submit_request(msg : string, triple : any, process_response : (data :any) => void) {
  console.log(msg + " ...");

  const method : string = triple.method;
  const path = triple.path;
  //const path = "http://localhost:8003" + triple.path;
  const body : string = triple.body;
  console.log("method: " + method);
  console.log("path: " + path);
  console.log("body: " + body);

  const options = {
    method: method,
    mode: "cors" as RequestMode,
    body: body,
    //headers: {
    //"sec-fetch-site": "cross-site",
    //"X-REMOTE-USER": "m-matsuda",
    //},
  };
  fetch(path, options)
    .then((response) => {
      if (!response.ok) {
        response.json().then(
          (data) => {
            pool_data.show_dialog = true;
            console.log("response-data: " + data);
            console.log(msg + " ... error: " + JSON.stringify(data));
            throw new Error(JSON.stringify(data));
          })
      } else {
        response.json().then(
          (data) => {
            console.log(msg + " ... done: " + JSON.stringify(data));
            if (data["CSRF-Token"] != null) {
              csrf_token = data["CSRF-Token"];
            }
            process_response(data);
          })}
    })
    .catch((err) => {
      console.log("Fetch error: ", err);
    });
}
