// Lenticularis-S3 Web-UI

// Copyright (c) 2022 RIKEN R-CCS
// SPDX-License-Identifier: BSD-2-Clause

//// Editor Data ////

var csrf_token;

var edit_pool_data = {
  pool_name_visible: false,
  edit_pool_visible: false,
  pool_list_visible: true,
  make_pool_mode: true,

  pool_name: "",
  buckets_directory: "",
  user: "",
  group: "",
  group_choices: [],

  expiration_date: "",
  permit_status: true,
  online_status: true,
  pool_state: "",

  list_of_buckets: [],
  bucket_name: "",
  bucket_policy: "none",

  access_keys_rw: [],
  access_keys_ro: [],
  access_keys_wo: [],
};

var make_new_pool_button_app = new Vue({
  el: "#make_new_pool_button",
  methods: {
    kick_add_new_pool: () => {
      edit_pool_data.make_pool_mode = true;
      run_get_user_template();
    },
  },
});

var show_pool_list_button_app = new Vue({
  el: "#show_pool_list_button",
  data: show_status_data,
  methods: {
    kick_show_pool_list: () => {
      edit_pool_data.make_pool_mode = false;
      run_get_pool_list();
    },
  },
});

var pool_section_app = new Vue({
  el: "#pool_section",
  data: edit_pool_data,
  methods: {
    kick_make_pool: () => {
      edit_pool_data.make_pool_mode = false;
      run_make_pool();
    },
  },
});

var buckets_section_app = new Vue({
  el: "#buckets_section",
  data: edit_pool_data,
  methods: {
    kick_make_bucket: run_make_bucket,
    kick_delete_bucket: run_delete_bucket,
  },
});

var keys_section_app = new Vue({
  el: "#keys_section",
  data: edit_pool_data,
  methods: {
    kick_make_key: run_make_access_key,
    kick_delete_key: run_delete_access_key,
  },
});

var pool_list_section_data = {
  pool_data_visible: true,
  pool_desc_list: [],
  pool_li_list: [],
};

var pool_list_section_app = new Vue({
  el: "#pool_list_section",
  data: pool_list_section_data,
  methods: {
    kick_edit_pool: run_edit_pool,
    kick_delete_pool: run_delete_pool,
  }
});

//// Server Response ////

var show_status_data = {
  status: "---",
  reason: "---",
  message: "---",
  time: "---",
};

var show_status_app = new Vue({
  el: "#show_status",
  data: show_status_data,
  methods: {
    kick_show_pool_list: run_get_pool_list,
    kick_debug: run_debug,
  },
});

//// FUNCTIONS ////

function submit_request(msg, triple, process_response) {
  show_message(msg + " ...");
  clear_status_field();

  const method = triple.method;
  const url_path = triple.url_path;
  const body = triple.body;
  console.log("method: " + method);
  console.log("url_path: " + url_path);
  console.log("body: " + body);
  const request_options = {
    method: method,
    body: body,
  };
  fetch(url_path, request_options)
    .then((response) => {
      if (!response.ok) {
        response.json().then(
          (data) => {
            console.log("response-data: " + data);
            show_message(msg + " ... error: " + JSON.stringify(data));
            render_response_status(data);
            throw new Error(JSON.stringify(data));
          })
      } else {
        response.json().then(
          (data) => {
            show_message(msg + " ... done: " + JSON.stringify(data));
            render_response_status(data);
            process_response(data);
          })}
    })
    .catch((err) => {
      console.log("Fetch error: ", err);
    });
}

function run_get_user_template() {
  const msg = "get user template"
  const method = "GET";
  const url_path = "/template";
  const c = {};
  const body = null;
  const triple = {method, url_path, body};
  return submit_request(msg, triple, set_user_template_data);
}

function run_get_pool_list() {
  const msg = "get pool list"
  const method = "GET";
  const url_path = "/pool";
  const body = null;
  const triple = {method, url_path, body};
  return submit_request(msg, triple, render_pool_list);
}

function run_make_pool() {
  const msg = "make pool";
  const directory = edit_pool_data.buckets_directory;
  const owner_gid = edit_pool_data.group;
  console.log("make_pool: directory=" + directory);
  const method = "POST";
  const url_path = ("/pool");
  const c = {"pool": {"buckets_directory": directory,
                      "owner_gid": owner_gid}};
  c["CSRF-Token"] = csrf_token;
  const body = JSON.stringify(c);
  const triple = {method, url_path, body};
  return submit_request(msg, triple, display_pool_in_edit_pool)
}

function run_delete_pool(i) {
  const msg = "delete pool";
  const pooldesc = pool_list_section_data.pool_desc_list[i]
  const pool_name = pooldesc["pool_name"];
  console.log(`pool_name = ${pool_name}`);
  const method = "DELETE";
  const url_path = "/pool/" + pool_name;
  const c = {};
  c["CSRF-Token"] = csrf_token;
  const body = JSON.stringify(c);
  const triple = {method, url_path, body};
  return submit_request(msg, triple, (data) => {run_get_pool_list();});
}

function run_edit_pool(i) {
  pooldesc = pool_list_section_data.pool_desc_list[i]
  const data = {"pool_list": [pooldesc]}
  display_pool_in_edit_pool(data)
}

function display_pool_in_edit_pool(data) {
  pooldesc = data["pool_list"][0]
  copy_pool_desc_for_edit(pooldesc);
  edit_pool_data.pool_name_visible = true;
  edit_pool_data.edit_pool_visible = true;
  pool_list_section_data.pool_data_visible = false;
}

function run_make_bucket() {
  const msg = "make bucket";
  const name = edit_pool_data.bucket_name;
  const policy = edit_pool_data.bucket_policy;
  console.log("make_bucket: name=" + name + ", policy=" + policy);
  const method = "PUT";
  const url_path = ("/pool/" + edit_pool_data.pool_name + "/bucket");
  const c = {"bucket": {"name": name, "bkt_policy": policy}};
  c["CSRF-Token"] = csrf_token;
  const body = JSON.stringify(c);
  const triple = {method, url_path, body};
  return submit_request(msg, triple, display_pool_in_edit_pool);
}

function run_delete_bucket(name) {
  const msg = "delete bucket";
  console.log("delete_bucket: name=" + name);
  const method = "DELETE";
  const url_path = ("/pool/" + edit_pool_data.pool_name + "/bucket/" + name);
  const c = {};
  c["CSRF-Token"] = csrf_token;
  const body = JSON.stringify(c);
  const triple = {method, url_path, body};
  return submit_request(msg, triple, display_pool_in_edit_pool);
}

function run_make_access_key(rw) {
  const msg = "make access-key";
  console.log("make_access_key: " + rw);
  const method = "PUT";
  const url_path = ("/pool/" + edit_pool_data.pool_name + "/secret");
  const c = {"key_policy": rw};
  c["CSRF-Token"] = csrf_token;
  const body = JSON.stringify(c);
  const triple = {method, url_path, body};
  return submit_request(msg, triple, display_pool_in_edit_pool);
}

function run_delete_access_key(key) {
  const msg = "delete access-key";
  console.log("delete_access_key: " + key);
  const method = "DELETE";
  const url_path = ("/pool/" + edit_pool_data.pool_name + "/secret/" + key);
  const c = {};
  c["CSRF-Token"] = csrf_token;
  const body = JSON.stringify(c);
  const triple = {method, url_path, body};
  return submit_request(msg, triple, display_pool_in_edit_pool);
}

const bkt_policy_names = ["none", "public", "upload", "download"];
const key_policy_names = ["readwrite", "readonly", "writeonly"];

function set_user_template_data(data) {
  const pool_desc_list = data["pool_list"];
  const desc = pool_desc_list[0];
  console.assert(desc["api_version"] == "v1.2", "Lens3 api mismatch");
  copy_user_template_for_edit(desc);
  edit_pool_data.pool_name_visible = true;
  edit_pool_data.edit_pool_visible = false;
  pool_list_section_data.pool_data_visible = false;
}

function render_pool_list(data) {
  const pool_desc_list = data["pool_list"];
  edit_pool_data.pool_name_visible = false;
  edit_pool_data.edit_pool_visible = false;

  const pool_li_items = new Array();
  for (var k = 0; k < pool_desc_list.length; k++) {
    const pooldesc = pool_desc_list[k];
    pool_li_items.push(render_pool_as_ul_entry(pooldesc));
  }

  pool_list_section_data.pool_li_list = pool_li_items;
  pool_list_section_data.pool_desc_list = pool_desc_list;
  pool_list_section_data.pool_data_visible = true;
}

function render_pool_as_ul_entry(pooldesc) {
  const bkts = pooldesc["buckets"];
  const bkts_none = (bkts.filter(d => d["bkt_policy"] == "none")
                     .map(d => d["name"]).join(" "));
  const bkts_upload = (bkts.filter(d => d["bkt_policy"] == "upload")
                       .map(d => d["name"]).join(" "));
  const bkts_download = (bkts.filter(d => d["bkt_policy"] == "download")
                         .map(d => d["name"]).join(" "));
  const bkts_public = (bkts.filter(d => d["bkt_policy"] == "public")
                       .map(d => d["name"]).join(" "));
  const bkt_entries = [
    {text: {label: "Private buckets", value: bkts_none}},
    {text: {label: "Public buckets", value: bkts_public}},
    {text: {label: "Public download buckets", value: bkts_download}},
    {text: {label: "Public upload buckets", value: bkts_upload}},
  ];

  const keys = pooldesc["access_keys"];
  const rwkeys = keys.filter(d => d["key_policy"] == "readwrite")
  const rokeys = keys.filter(d => d["key_policy"] == "readonly")
  const wokeys = keys.filter(d => d["key_policy"] == "writeonly")
  const key_entries = [
    ... rwkeys.reduce((part, d) => part.concat([
      {text: {label: "Access key (rw)", value: d["access_key"]}},
      {text: {label: "Secret key", value: d["secret_key"]}},
    ]), []),
    ... rokeys.reduce((part, d) => part.concat([
      {text: {label: "Access key (ro)", value: d["access_key"]}},
      {text: {label: "Secret key", value: d["secret_key"]}},
    ]), []),
    ... wokeys.reduce((part, d) => part.concat([
      {text: {label: "Access key (wo)", value: d["access_key"]}},
      {text: {label: "Secret key", value: d["secret_key"]}},
    ]), []),
  ];

  return [
    {text: {label: "Buckets directory", value: pooldesc["buckets_directory"]}},
    {text: {label: "Unix user", value: pooldesc["owner_uid"]}},
    {text: {label: "Unix group", value: pooldesc["owner_gid"]}},
    ... bkt_entries,
    ... key_entries,
    //{text: {label: "Endpoint-URL", value: pooldesc["endpoint_url"]}},
    {text: {label: "Pool-ID", value: pooldesc["pool_name"]}},
    //{text: {label: "Direct hostname", value: pooldesc["direct_hostnames"].join(" ")}},
    {text: {label: "MinIO state",
            value: (pooldesc["minio_state"]
                    + " (reason: " + pooldesc["minio_reason"] + ")")}},
    {text: {label: "Expiration date", value: format_rfc3339_if_not_zero(pooldesc["expiration_date"])}},
    {text: {label: "User enabled", value: pooldesc["permit_status"]}},
    {text: {label: "Pool online", value: pooldesc["online_status"]}},
    {text: {label: "Creation date", value: format_rfc3339_if_not_zero(pooldesc["modification_time"])}},
  ];
}

function copy_user_template_for_edit(desc) {
  edit_pool_data.user = desc["owner_uid"];
  edit_pool_data.group = desc["owner_gid"];
  edit_pool_data.group_choices = desc["groups"];
}

function copy_pool_desc_for_edit(pooldesc) {
  edit_pool_data.pool_name = pooldesc["pool_name"];
  edit_pool_data.user = pooldesc["owner_uid"];
  edit_pool_data.group = pooldesc["owner_gid"];
  edit_pool_data.buckets_directory = pooldesc["buckets_directory"];
  edit_pool_data.list_of_buckets = pooldesc["buckets"];

  edit_pool_data.bucket_name = "";
  edit_pool_data.bucket_policy = "none";
  edit_pool_data.group_choices = pooldesc["groups"];

  const keys = pooldesc["access_keys"];
  const rwkeys = keys.filter(d => d["key_policy"] == "readwrite")
  const rokeys = keys.filter(d => d["key_policy"] == "readonly")
  const wokeys = keys.filter(d => d["key_policy"] == "writeonly")
  edit_pool_data.access_keys_rw = rwkeys
  edit_pool_data.access_keys_ro = rokeys
  edit_pool_data.access_keys_wo = wokeys

  edit_pool_data.expiration_date = format_rfc3339_if_not_zero(pooldesc["expiration_date"]);
  edit_pool_data.permit_status = pooldesc["permit_status"];
  edit_pool_data.online_status = pooldesc["online_status"];
  edit_pool_data.pool_state = pooldesc["minio_state"];
}

function show_message(s) {
  show_status_data.message = "Message: " + s;
}

function clear_status_field() {
  render_response_status({"status": "", "reason": "", "time": "0"})
}

function render_response_status(data) {
  if (data["CSRF-Token"] != null) {
    csrf_token = data["CSRF-Token"];
  }
  if (data["pool_list"] != null && data["pool_list"][0] != null) {
    edit_pool_data.pool_state = data["pool_list"][0]["minio_state"];
  }
  show_status(data["status"])
  show_reason(data["reason"])
  show_duration(data["time"])
}

function show_status(s) {
  show_status_data.status = "Status: " + s;
}

function show_reason(s) {
  show_status_data.reason = "Reason: " + s;
}

function show_duration(s) {
  if (s != null) {
    show_status_data.time = "Finished at: " + format_rfc3339_if_not_zero(s);
  } else {
    show_status_data.time = "";
  }
}

function parse_rfc3339(s) {
  return "" + new Date(s).getTime() / 1000;
}

function format_rfc3339(d) {
  return new Date(d * 1000).toISOString();
}

function format_rfc3339_if_not_zero(d) {
  //console.log("format_rfc3339_if_not_zero: " + d);
  if (d == "0") {
    return "0";
  }
  return format_rfc3339(d);
}

function run_debug() {
  console.log("Dump internal data");
  //var post_data = compose_create_dict__(csrf_token);
  //var put_data = compose_update_dict__(csrf_token);
  //var bkt_data = compose_create_bucket_dict(csrf_token);
  //var key_data = compose_access_key_update_dict(csrf_token);
  //var delete_data = compose_empty_body(csrf_token);
  //console.log("post_data: " + post_data);
  //console.log("put_data: " + put_data);
  //console.log("bkt_data: " + bkt_data);
  //console.log("key_data: " + key_data);
  //console.log("delete_data: " + delete_data);
  //parsed = Date.parse("2012-07-04T18:10:00.000+09:00")
  //console.log("parsed: " + parsed);
  //var e = "1638401795";
  //var date = new Date(e * 1000);
  //var formatted = date.toISOString();
  //console.log("toISOString: " + e + " => " + formatted);
  //var t = "2012-07-04T18:10:00.000+09:00";
  //var parsed = Date.parse(s)
  //var date2 = new Date(s)
  //var d2 = date2.getTime() / 1000;
  //console.log("new Date: " + s + " => " + d2);
  const s = "2022-03-31T00:00:00.000Z";
  const t = parse_rfc3339(s);
  const u = format_rfc3339(t);
  console.log("parse: " + s + " => " + t);
  console.log("unparse: " + t + " => " + u);
}
