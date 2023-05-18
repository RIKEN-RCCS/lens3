/* Lens3 Client */

/* Copyright (c) 2022-2023 RIKEN R-CCS */
/* SPDX-License-Identifier: BSD-2-Clause */

import {reactive, computed} from "vue";

let csrf_token;
const base_path = "";

/* Editor Data */

const pool_data_ = {
  buckets_directory: "",
  user: "",
  group: "",
  group_choices: [],

  pool_name_visible: true,
  edit_pool_visible: false,
  pool_args_visible: false,

  make_pool_mode: false,

  desserts: [
    {name: "Buckets directory", calories: "/home/users/m-matsuda/pool-a"},
    {name: "Unix user", calories: "m-matsuda"},
    {name: "Unix group", calories: "m-matsuda"},
    {name: "Private buckets", calories: "bkt0 bkt1 bkt3"},
    {name: "Public buckets", calories: ""},
    {name: "Public download buckets", calories: ""},
    {name: "Public upload buckets", calories: ""},
    {name: "Pool-ID", calories: "UFW3ZA6tYEQ2jqV3QmUU"},
    {name: "MinIO state", calories: "ready (reason: -)"},
    {name: "Expiration date", calories: "2043-05-01T07:18:24.000Z"},
    {name: "User enabled", calories: "true"},
    {name: "Pool online", calories: "true"},
    {name: "Creation date", calories: "2023-05-06T07:18:24.000Z"},
  ],

  pool_list: [
    {
      desserts: [
        {name: "Buckets directory", calories: "/home/users/m-matsuda/pool-a"},
        {name: "Unix user", calories: "m-matsuda"},
        {name: "Unix group", calories: "m-matsuda"},
        {name: "Private buckets", calories: "bkt0 bkt1 bkt3"},
        {name: "Public buckets", calories: ""},
        {name: "Public download buckets", calories: ""},
        {name: "Public upload buckets", calories: ""},
        {name: "Pool-ID", calories: "UFW3ZA6tYEQ2jqV3QmUU"},
        {name: "MinIO state", calories: "ready (reason: -)"},
        {name: "Expiration date", calories: "2043-05-01T07:18:24.000Z"},
        {name: "User enabled", calories: "true"},
        {name: "Pool online", calories: "true"},
        {name: "Creation date", calories: "2023-05-06T07:18:24.000Z"},
      ],
    },
  ],

  api_get_user_info() {
    const msg = "get_user_info"
    const method = "GET";
    const path = (base_path + "/user-info");
    const body = null;
    const triple = {method, path, body};
    submit_request(msg, triple, set_user_info_data);
  },

  api_make_pool() {
    console.log("make_pool: this=" + this);
    const msg = "make_pool";
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
    return submit_request(msg, triple, set_pool_data)
  }

};

export const pool_data = reactive(pool_data_);

function set_user_info_data(data : any) {
  console.assert(data && data["user_info"]);
  const d = data["user_info"];
  console.assert(d["api_version"] == "v1.2", "Lens3 api mismatch");
  pool_data.user = d["uid"];
  pool_data.group = d["groups"][0];
  pool_data.group_choices = d["groups"];

  pool_data.pool_name_visible = true;
  pool_data.edit_pool_visible = false;
  pool_data.pool_args_visible = false;
}

function set_pool_data(data) {
  console.assert(data && data["pool_list"] && data["pool_list"].length == 1);
  const d = data["pool_list"][0]
  pool_data.pool_name_visible = true;
  pool_data.edit_pool_visible = true;

  pool_data.pool_name = d["pool_name"];
  pool_data.user = d["owner_uid"];
  pool_data.group = d["owner_gid"];
  pool_data.buckets_directory = d["buckets_directory"];
  pool_data.list_of_buckets = d["buckets"];

  pool_data.bucket_name = "";
  pool_data.bucket_policy = "none";
  pool_data.group_choices = d["groups"];

  const keys = d["access_keys"];
  const rwkeys = keys.filter(d => d["key_policy"] == "readwrite")
  const rokeys = keys.filter(d => d["key_policy"] == "readonly")
  const wokeys = keys.filter(d => d["key_policy"] == "writeonly")
  pool_data.access_keys_rw = format_time_in_keys(rwkeys)
  pool_data.access_keys_ro = format_time_in_keys(rokeys)
  pool_data.access_keys_wo = format_time_in_keys(wokeys)

  //edit_pool_data.user_enabled_status = d["user_enabled_status"];
  //edit_pool_data.online_status = d["online_status"];
  //edit_pool_data.pool_state = d["minio_state"];
}

function format_time_in_keys(keys) {
  return keys.map((k) => {
    return {"access_key": k["access_key"],
            "secret_key": k["secret_key"],
            "expiration_time": format_time_z(k["expiration_time"])};
  });
}

function api_list_pools() {
  const msg = "list pools";
  const method = "GET";
  const path = (base_path + "/pool");
  const body = null;
  const triple = {method, path, body};
  submit_request(msg, triple, render_pool_list);
}

function render_pool_list(data : any) {
}

function submit_request(msg : string, triple : any, process_response : (data :any) => void) {
  console.log(msg + " ...");

  const method = triple.method;
  //const path = triple.path;
  const path = "http://localhost:8003" + triple.path;
  const body = triple.body;
  console.log("method: " + method);
  console.log("path: " + path);
  console.log("body: " + body);

  const options = {
    method: method,
    mode: "cors",
    body: body,
    headers: {
      //"sec-fetch-site": "cross-site",
      "X-REMOTE-USER": "m-matsuda",
    },
  };
  fetch(path, options)
    .then((response) => {
      if (!response.ok) {
        response.json().then(
          (data) => {
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
