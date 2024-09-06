/* Lens3 Web-UI */

// Copyright (c) 2022-2023 RIKEN R-CCS
// SPDX-License-Identifier: BSD-2-Clause

// A constant "base_path_" is set in the script code in "index.html".
// A base-path is a base-URL used when running behind a proxy.  Its
// value is taken from the configuration.  It can be something like
// "", ".", "/api~", etc., without a trailing slash.

// List of used html-element ID's
// id="pool_make_section"
// id="pool_list_section"
// id="buckets_section"
// id="secrets_section"
// id="bucket_name"
// id="bucket_policy"
// id="buckets_directory"
// id="group_choices"
// id="list_of_buckets"
// id="list_of_pools"
// id="pool_directory"
// id="pool_owner"
// id="secret_expiration"
// id="list_of_secrets_ro"
// id="list_of_secrets_rw"
// id="list_of_secrets_wo"
// id="server_response"

/* Editor Data. */

// Let "pool_data" not a constant to make it visible in js console.

let pool_data = {
  owner: "",
  group_choices: [],

  x_csrf_token: "",

  /* Partial data on a selected pool. */

  pool_name: "",
  buckets_directory: "",
  pool_desc_list: [],
  bucket_list: [],
  secrets_rw: [],
  secrets_ro: [],
  secrets_wo: [],

  //group: "",
  //expiration_time: "",
  //user_enabled_status: true,
  //online_status: true,
  //pool_state: "",

  /* Server response. */

  response_status: "",
  response_reason: "",
  response_time: "",
};

// const bkt_policy_names = ["none", "public", "upload", "download"];
// const key_policy_names = ["readwrite", "readonly", "writeonly"];

// Initializes the UI state.

function start_ui() {
  //console.log("start_ui()");
  display_pool_make(false);
  display_pool_list(false);
  display_pool_edit(false);
  api_get_user_info();
}

/* Click Actions. */

function kick_show_pool_make() {
  display_pool_make(true);
  api_get_user_info();
}

function kick_show_pool_list() {
  display_pool_make(false);
  api_list_pools();
  display_pool_list(true);
  display_pool_edit(false);
}

function kick_edit_pool(p) {
  run_edit_pool(p);
}

function kick_make_pool() {
  const directory = document.getElementById("pool_directory").value;
  const gid = document.getElementById("group_choices").value;
  display_pool_make(false);
  api_make_pool(directory, gid);
}

function kick_delete_pool(p) {
  api_delete_pool(p);
}

function kick_make_bucket() {
  const name = document.getElementById("bucket_name").value;
  const policy = document.getElementById("bucket_policy").value;
  api_make_bucket(name, policy);
}

function kick_delete_bucket(name){
  api_delete_bucket(name);
}

function kick_make_secret(rw) {
  const expiry = document.getElementById("secret_expiration").value;
  api_make_secret(rw, expiry);
}

function kick_delete_secret(key) {
  api_delete_secret(key);
}

function kick_copy_to_clipboard(key) {
  copy_to_clipboard(key);
}

/* Rendering Control. */

function display_pool_list(v) {
  const e = document.getElementById("pool_list_section");
  e.style.display = v ? "" : "none";
}

function display_pool_edit(v) {
  const e1 = document.getElementById("buckets_section");
  e1.style.display = v ? "" : "none";
  const e2 = document.getElementById("secrets_section");
  e2.style.display = v ? "" : "none";
}

function display_pool_make(v) {
  const e2 = document.getElementById("pool_make_section");
  e2.style.display = v ? "" : "none";
}

function render_user_info() {
  // | <input id="pool_owner" size="30" disabled />
  // | <select id="group_choices" required="true">
  // |   <option>some-group-name</option>
  // | </select>
  //console.log("render_user_info: user=" + pool_data.owner);
  //console.log(pool_data.group_choices);
  const e1 = document.getElementById("pool_owner");
  e1.value = pool_data.owner;
  const e2 = document.getElementById("group_choices");
  const s = document.createElement("select");
  s.id="group_choices";
  for (const v of pool_data.group_choices) {
    const o = document.createElement("option");
    o.text = v;
    o.value = v;
    s.appendChild(o);
  }
  e2.replaceWith(s);
}

function render_secret_expiration_default() {
  const e = document.getElementById("secret_expiration");
  const day7 = Math.floor(Date.now() / 1000) + (7 * 24 * 3600);
  e.valueAsDate = new Date(day7 * 1000);
}

function render_pool_list(pool_li_items) {
  // | <div> for each index p in pool_li_items
  // |   <hr />
  // |   <input type="button" value="Edit" onclick="kick_edit_pool(p)" />
  // |   <input type="button" value="Delete" onclick="kick_delete_pool(p)" />
  // |   <ul style="list-style: none;">
  // |     <li v-for="item in pool_li_items[p]">
  // |       <span class="label">item.text.label:</span>
  // |       item.text.value
  // |     </li>
  // |   </ul>
  // | </div>
  //console.log("RENDER_POOL_LIST");
  //console.log(pool_li_items);
  const e = document.getElementById("list_of_pools");
  const d1 = document.createElement("div");
  for (const p in pool_li_items) {
    const d2 = document.createElement("div");
    // <hr />
    const hr = document.createElement("hr");
    d2.appendChild(hr);
    // <input>
    const i1 = document.createElement("input");
    i1.onclick = () => {kick_edit_pool(p);};
    i1.type = "button";
    i1.value = "Edit";
    d2.appendChild(i1);
    // <input>
    const i2 = document.createElement("input");
    i2.onclick = () => {kick_delete_pool(p);};
    i2.type = "button";
    i2.value = "Delete";
    d2.appendChild(i2);
    // <ul>
    const ul = document.createElement("ul");
    ul.style = "list-style: none;";
    for (const i of pool_li_items[p]) {
      const li = document.createElement("li");
      const s = `<span class="label">${i.text.label}: </span>${i.text.value}`;
      li.innerHTML = s;
      ul.appendChild(li);
    }
    d2.appendChild(ul);
    // done.
    d1.appendChild(d2);
  }
  e.replaceChildren(d1);
}

function render_bucket_list() {
  // | <div> for each b in bucket_list
  // |   <input value="b.name" size="30" disabled />
  // |   <input value="b.bkt_policy" size="10" disabled />
  // |   <button onclick="kick_delete_bucket(b.name)">Delete bucket</button>
  // | </div>
  //console.log("render_bucket_list");
  //console.log(pool_data.bucket_list);

  const e = document.getElementById("list_of_buckets");
  const list = [];
  for (const b of pool_data.bucket_list) {
    const d1 = document.createElement("div");
    {
      const s1 = document.createElement("span");
      s1.className = "label";
      // <input>
      const i1 = document.createElement("input");
      i1.type = "text";
      i1.value = b.name;
      i1.size = 30;
      i1.disabled = true;
      s1.appendChild(i1);
      // <input>
      const i2 = document.createElement("input");
      i2.type = "text";
      i2.value = b.bkt_policy;
      i2.size = 10;
      i2.disabled = true;
      s1.appendChild(i2);
      d1.appendChild(s1);
    }
    // <button>
    const b1 = document.createElement("button");
    b1.onclick = () => {kick_delete_bucket(b.name);};
    b1.innerText = "Delete bucket";
    d1.appendChild(b1);
    list.push(d1);
  }
  e.replaceChildren(... list);
}

function render_secret_list() {
  render_secret_list_by_policy("rw", pool_data.secrets_rw);
  render_secret_list_by_policy("ro", pool_data.secrets_ro);
  render_secret_list_by_policy("wo", pool_data.secrets_wo);
}

function render_secret_list_by_policy(policy, keys) {
  // | <div> for each k in keys
  // |   <input value="k.access_key" size="22" disabled />
  // |   <button onclick="kick_copy_to_clipboard(k.access_key)">Copy</button>
  // |   <input value="k.secret_key" size="50" disabled />
  // |   <button onclick="kick_copy_to_clipboard(k.secret_key)">Copy</button>
  // |   <span>Expires:</span>
  // |   <input type="datetime" value="k.expiration_time" disabled />
  // |   <button onclick="kick_delete_secret(k.access_key)">Delete key</button>
  // | </div>
  console.assert(["rw", "ro", "wo"].includes(policy));
  const section = "list_of_secrets_" + policy;
  const e = document.getElementById(section);
  const list = [];
  for (const k of keys) {
    //console.log("k.SECRET_KEY=" + k.secret_key);
    const d1 = document.createElement("div");
    {
      const s1 = document.createElement("span");
      s1.className = "label";
      // <input>
      const i1 = document.createElement("input");
      i1.type = "text";
      i1.value = k.access_key;
      i1.size = 22;
      i1.disabled = true;
      s1.appendChild(i1);
      // <button>
      const b1 = document.createElement("button");
      b1.onclick = () => {kick_copy_to_clipboard(k.access_key);};
      b1.innerText = "Copy";
      s1.appendChild(b1);
      d1.appendChild(s1);
    }
    // <input>
    const i2 = document.createElement("input");
    i2.type = "text";
    i2.value = k.secret_key;
    i2.size = 50;
    i2.disabled = true;
    d1.appendChild(i2);
    // <button>
    const b2 = document.createElement("button");
    b2.onclick = () => {kick_copy_to_clipboard(k.secret_key);};
    b2.innerText = "Copy";
    d1.appendChild(b2);
    // <span>
    const s2 = document.createElement("span");
    s2.innerHTML = "&emsp;Expires:";
    d1.appendChild(s2);
    // <input>
    const i3 = document.createElement("input");
    i3.type = "datetime";
    i3.value = k.expiration_time;
    i3.disabled = true;
    d1.appendChild(i3);
    // <button>
    const b3 = document.createElement("button");
    b3.onclick = () => {kick_delete_secret(k.access_key);};
    b3.innerText = "Delete key";
    d1.appendChild(b3);
    list.push(d1);
  }
  e.replaceChildren(... list);
}

function render_buckets_directory() {
  const e = document.getElementById("buckets_directory");
  e.value = pool_data.buckets_directory;
}

function render_response() {
  const e = document.getElementById("server_response");
  const d1 = document.createElement("div");
  d1.innerText = "Status: " + pool_data.response_status;
  const d2 = document.createElement("div");
  d2.innerText = "Reason: " + pool_data.response_reason;
  const d3 = document.createElement("div");
  d3.innerText = "Timestamp: " + pool_data.response_time;
  const d4 = document.createElement("div");
  d4.innerText = "Message: " + pool_data.response_message;
  e.replaceChildren(d1, d2, d3, d4);
}

/* API Operations. */

function submit_request(msg, triple, process_response) {
  show_message(null, msg + " ...");

  const method = triple.method;
  const path = triple.path;
  const body = triple.body;
  const headers = {
    "Content-Type": "application/json",
  };
  if (pool_data.x_csrf_token != "") {
    Object.assign(headers, {"X-CSRF-Token": pool_data.x_csrf_token});
  };
  console.log("method: " + method);
  console.log("path: " + path);
  console.log("body: " + body);
  console.log("headers: " + JSON.stringify(headers));

  const options = {
    method: method,
    body: body,
    headers: headers,
  };
  fetch(path, options)
    .then((response) => {
      if (!response.ok) {
        response.json().then(
          (data) => {
            console.log("response-data: " + JSON.stringify(data));
            show_message(data, msg + " ... error: " + JSON.stringify(data));
            throw new Error(JSON.stringify(data));
          })
      } else {
        response.json().then(
          (data) => {
            show_message(data, msg + " ... done: " + JSON.stringify(data));
            process_response(data);
          })}
    })
    .catch((err) => {
      console.log("Fetch error: ", err);
    });
}

function api_get_user_info() {
  const msg = "get user info";
  const method = "GET";
  const path = (base_path_ + "/user-info");
  const body = null;
  const triple = {method, path, body};
  return submit_request(msg, triple, set_user_info_data);
}

function api_list_pools() {
  const msg = "list pools";
  const method = "GET";
  const path = (base_path_ + "/pool");
  const body = null;
  const triple = {method, path, body};
  return submit_request(msg, triple, set_pool_list_data);
}

function api_make_pool(directory, gid) {
  const msg = "make pool";
  //const directory = pool_data.buckets_directory;
  //const gid = pool_data.group;
  console.log("make_pool: directory=" + directory);
  const method = "POST";
  const path = (base_path_ + "/pool");
  const args = {"buckets_directory": directory,
                "owner_gid": gid};
  const body = JSON.stringify(args);
  const triple = {method, path, body};
  return submit_request(msg, triple, set_pool_data);
}

function api_delete_pool(i) {
  const msg = "delete pool";
  const desc = pool_data.pool_desc_list[i];
  const pool_name = desc["pool_name"];
  console.log("pool_name=" + pool_name);
  const method = "DELETE";
  const path = (base_path_ + "/pool/" + pool_name);
  const args = {};
  const body = JSON.stringify(args);
  const triple = {method, path, body};
  return submit_request(msg, triple, (data) => {api_list_pools();});
}

function run_edit_pool(i) {
  render_secret_expiration_default();
  desc = pool_data.pool_desc_list[i];
  const data = {"pool_desc": desc};
  set_pool_data(data);
}

function api_make_bucket(name, policy) {
  console.assert(pool_data.pool_name != "");
  const msg = "make bucket";
  console.log("make_bucket: name=" + name + ", policy=" + policy);
  const method = "PUT";
  const path = (base_path_ + "/pool/" + pool_data.pool_name
                + "/bucket");
  const args = {"name": name,
                "bkt_policy": policy};
  const body = JSON.stringify(args);
  const triple = {method, path, body};
  return submit_request(msg, triple, set_pool_data);
}

function api_delete_bucket(name) {
  console.assert(pool_data.pool_name != "");
  const msg = "delete bucket";
  console.log("delete_bucket: name=" + name);
  const method = "DELETE";
  const path = (base_path_ + "/pool/" + pool_data.pool_name
                + "/bucket/" + name);
  const args = {};
  const body = JSON.stringify(args);
  const triple = {method, path, body};
  return submit_request(msg, triple, set_pool_data);
}

function api_make_secret(rw, expiry) {
  console.assert(pool_data.pool_name != "");
  const msg = "make secret";
  console.log("make_secret: " + rw + ", " + expiry);
  const expiration = parse_time_z(expiry);
  const method = "POST";
  const path = (base_path_ + "/pool/" + pool_data.pool_name
                + "/secret");
  const args = {"key_policy": rw,
                "expiration_time": expiration};
  const body = JSON.stringify(args);
  const triple = {method, path, body};
  return submit_request(msg, triple, set_pool_data);
}

function api_delete_secret(key) {
  console.assert(pool_data.pool_name != "");
  const msg = "delete access-key";
  console.log("delete_access_key: " + key);
  const method = "DELETE";
  const path = (base_path_ + "/pool/" + pool_data.pool_name
                + "/secret/" + key);
  const args = {};
  const body = JSON.stringify(args);
  const triple = {method, path, body};
  return submit_request(msg, triple, set_pool_data);
}

function copy_to_clipboard(s) {
  navigator.clipboard.writeText(s);
}

function set_user_info_data(data) {
  //console.log("set_user_info_data");
  console.assert(data && data["user_info"]);
  const u = data["user_info"];
  console.assert(u["api_version"] == "v1.2", "Lens3 api mismatch");
  copy_user_info_for_edit(u);
  display_pool_list(false);
  display_pool_edit(false);
}

function set_pool_list_data(data) {
  //console.log("set_pool_list_data");
  const pool_desc_list = data["pool_list"];
  pool_data.pool_desc_list = pool_desc_list;
  const pool_li_items = new Array();
  for (var k = 0; k < pool_desc_list.length; k++) {
    const desc = pool_desc_list[k];
    pool_li_items.push(make_pool_entry_for_printing(desc));
  }
  render_pool_list(pool_li_items);
  display_pool_list(true);
  display_pool_edit(false);
}

function set_pool_data(data) {
  desc = data["pool_desc"];
  copy_pool_data_for_edit(desc);
  render_bucket_list();
  render_secret_list();
  display_pool_list(false);
  display_pool_edit(true);
}

function make_pool_entry_for_printing(desc) {
  const bkts = desc["buckets"];
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
  /*
  const keys = desc["secrets"];
  const rwkeys = keys.filter(d => d["key_policy"] == "readwrite");
  const rokeys = keys.filter(d => d["key_policy"] == "readonly");
  const wokeys = keys.filter(d => d["key_policy"] == "writeonly");
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
  */
  return [
    {text: {label: "Buckets directory", value: desc["buckets_directory"]}},
    {text: {label: "Unix user", value: desc["owner_uid"]}},
    {text: {label: "Unix group", value: desc["owner_gid"]}},
    ... bkt_entries,
    /* ... key_entries, */
    {text: {label: "Pool-ID", value: desc["pool_name"]}},
    {text: {label: "MinIO state",
            value: (desc["minio_state"]
                    + " (reason: " + desc["minio_reason"] + ")")}},
    {text: {label: "Expiration date",
            value: format_time_z(desc["expiration_time"])}},
    {text: {label: "User enabled", value: desc["user_enabled_status"]}},
    {text: {label: "Pool online", value: desc["online_status"]}},
    {text: {label: "Creation date",
            value: format_time_z(desc["modification_time"])}},
  ];
}

function copy_user_info_for_edit(u) {
  console.log("copy_user_info_for_edit");
  console.log(u);
  pool_data.owner = u["uid"];
  //pool_data.group = u["groups"][0];
  pool_data.group_choices = u["groups"];
  render_user_info();
}

function copy_pool_data_for_edit(desc) {
  pool_data.pool_name = desc["pool_name"];
  pool_data.buckets_directory = desc["buckets_directory"];
  pool_data.owner = desc["owner_uid"];
  pool_data.group_choices = desc["groups"];
  pool_data.bucket_list = desc["buckets"];

  const keys = desc["secrets"];
  const rw = keys.filter(d => d["key_policy"] == "readwrite");
  const ro = keys.filter(d => d["key_policy"] == "readonly");
  const wo = keys.filter(d => d["key_policy"] == "writeonly");
  pool_data.secrets_rw = format_time_in_keys(rw);
  pool_data.secrets_ro = format_time_in_keys(ro);
  pool_data.secrets_wo = format_time_in_keys(wo);

  render_buckets_directory();

  //pool_data.user_enabled_status = desc["user_enabled_status"];
  //pool_data.online_status = desc["online_status"];
  //pool_data.pool_state = desc["minio_state"];
}

function format_time_in_keys(keys) {
  return keys.map((k) => {
    return {"access_key": k["access_key"],
            "secret_key": k["secret_key"],
            "expiration_time": format_time_z(k["expiration_time"])};
  });
}

// Shows a server response with a message.  A response field is
// cleared if data=null.

function show_message(data, s) {
  pool_data.response_message = s;
  if (data) {
    pool_data.response_status = data["status"];
    pool_data.response_reason = data["reason"];
    if (data["time"]) {
      pool_data.response_time = format_time_z(data["time"]);
    } else {
      pool_data.response_time = "";
    }
    if (data["x_csrf_token"]) {
      pool_data.x_csrf_token = data["x_csrf_token"];
    }
  } else {
    pool_data.response_status = "";
    pool_data.response_reason = "";
    pool_data.response_time = "0";
  }
  render_response();
}

//** Returns an integer for date+time, but in a string.

function parse_time_z(s) {
  return "" + new Date(s).getTime() / 1000;
}

//** Returns a date+time string (without milliseconds).

function format_time_z(d) {
  if (d == "0") {
    return "0";
  } else {
    return (new Date(d * 1000).toISOString().substring(0, 19) + "Z");
  }
}

// Causes an error.  It calls API with a wrong csrf-token header
// value.

function kick_test_csrf() {
  console.log("test_csrf");
  const save = pool_data.x_csrf_token;
  pool_data.x_csrf_token = "af3d34829c5f8ee19f8de0f97849bf7fc8a7e268";
  api_list_pools();
  pool_data.x_csrf_token = save;
}

function kick_dump() {
  console.log("DUMP INTERNAL DATA");
  console.log("base_path_=" + base_path_);
  console.log("document.cookie=" + document.cookie);
  //console.log("browser.cookies=" + browser.cookies);
  //console.log("CookieStore.getAll()=" + CookieStore.getAll());

  const t1 = "2023-06-14T15:15:15.000Z";
  const t2 = parse_time_z(t1);
  const t3 = format_time_z(t2);
  console.log("parse_time: " + t1 + " => " + t2);
  console.log("format_time: " + t2 + " => " + t3);
}
