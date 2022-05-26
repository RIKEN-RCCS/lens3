// Lenticularis-S3 Web-UI

// Copyright (c) 2022 RIKEN R-CCS
// SPDX-License-Identifier: BSD-2-Clause

//// Editor ////

var csrf_token;

var edit_pool_data = {
  pool_name: "",
  pool_name_visible: false,
  edit_pool_visible: false,
  user: "",
  group: "",
  buckets_directory: "",
  buckets: ["", "", "", ""],
  accessKeys: [],
  accessKeyIDrw: "",
  accessKeyIDro: "",
  accessKeyIDwo: "",
  secretAccessKeyrw: "",
  secretAccessKeyro: "",
  secretAccessKeywo: "",
  key: "",
  policy: "",
  direct_hostnames: "",
  expiration_date: "",
  permit_status: "",
  online_status: "",
  mode: "",
  atime: "",
  groups: "",
  directHostnameDomains: "",
  facadeHostname: "",
  endpointURLs: "",
  submit_button_name: "",
  submit_button_disabled: false,
  submit_button_visible: false,
  deleteButtonDisabled: false,
  buckets_directory_disabled: false,
};

var edit_pool_app = new Vue({
  el: '#create_pool',
  data: edit_pool_data,
  methods: {
    kick_create_pool: run_create_pool,
    submitChangeAccessKeyRW: run_change_access_key_rw,
    submitChangeAccessKeyRO: run_change_access_key_ro,
    submitChangeAccessKeyWO: run_change_access_key_wo,
    kick_make_access_key_rw: run_change_access_key_rw,
    kick_make_access_key_ro: run_change_access_key_ro,
    kick_make_access_key_wo: run_change_access_key_wo,
  },
});

var edit_buckets_app = new Vue({
  el: '#edit_buckets',
  data: edit_pool_data,
  methods: {
    kick_create_pool: run_create_pool,
    kick_create_bucket: run_create_bucket,
    submitChangeAccessKeyRW: run_change_access_key_rw,
    submitChangeAccessKeyRO: run_change_access_key_ro,
    submitChangeAccessKeyWO: run_change_access_key_wo,
    kick_make_access_key_rw: run_change_access_key_rw,
    kick_make_access_key_ro: run_change_access_key_ro,
    kick_make_access_key_wo: run_change_access_key_wo,
  },
});

var edit_keys_app = new Vue({
  el: '#edit_keys',
  data: edit_pool_data,
  methods: {
    kick_create_pool: run_create_pool,
    submitChangeAccessKeyRW: run_change_access_key_rw,
    submitChangeAccessKeyRO: run_change_access_key_ro,
    submitChangeAccessKeyWO: run_change_access_key_wo,
    kick_make_access_key_rw: run_change_access_key_rw,
    kick_make_access_key_ro: run_change_access_key_ro,
    kick_make_access_key_wo: run_change_access_key_wo,
  },
});

//// Show Status ////

var show_status_data = {
  message: "---",
  status: "---",
  reason: "---",
  time: "---",
};

var show_status_app = new Vue({
  el: "#show_status",
  data: show_status_data,
  methods: {
    kick_show_pool_list: get_pool_list,
    kick_debug: run_debug,
  },
});

var show_app = new Vue({
  el: "#show_pool_list_button",
  data: show_status_data,
  methods: {
    kick_show_pool_list: get_pool_list,
    kick_debug: run_debug,
  },
});

var add_pool_app = new Vue({
  el: "#add_new_pool_button",
  methods: {
    kick_add_new_pool: get_template,
  },
});

//// Pool List ////

// dynamically allocated

var list_pools_data = {pool_data_visible: false}; // sentinel
var list_pools_app;

//// FUNCTIONS ////

function run_create_pool() {
  var create = edit_pool_data["submit_button_name"] == "Create";
  console.log("CREATE = " + create);
  if (create) {
    return submit_operation(0, null)
  }
  else {
    return submit_operation(1, null)
  }
}

function run_create_bucket() {
  console.log("create_bucket: name=" + edit_pool_data.key
              + ", policy=" + edit_pool_data.policy);
  return submit_operation(2, () => {
    var key = edit_pool_data.key;
    var policy = edit_pool_data.policy;
    method = "PUT";
    url_path = ("/pool/" + edit_pool_data.pool_name + "/bucket");
    var c = {"bucket": {"key": key, "policy": policy}};
    //body = stringify_dict(c, csrf_token);
    c["CSRF-Token"] = csrf_token;
    body = JSON.stringify(c);
    return {method, url_path, body};
  });
}

function run_change_access_key_rw() {
  console.log("change_access_key RW");
  return submit_operation(3, null)
}

function run_change_access_key_ro() {
  console.log("change_access_key RO");
  return submit_operation(4, null)
}

function run_change_access_key_wo() {
  console.log("change_access_key WO");
  return submit_operation(5, null)
}

function submit_operation(op, triple) {
  edit_pool_data.submit_button_disabled = true;
  show_message(edit_pool_data["submit_button_name"] + " pool ...");
  clear_status_field();

  var method;
  var url_path;
  var body;

  if (op == 0) {
    // Create pool.
    method = "POST";
    url_path = "/pool";
    body = compose_create_dict(csrf_token);
  }
  else if (op == 1) {
    // Update pool.
    method = "PUT";
    url_path = "/pool/" + edit_pool_data.pool_name;
    body = compose_update_dict(csrf_token);
  }
  else if (op == 2) {
    // Create bucket.
    //var key = edit_pool_data.key;
    //var policy = edit_pool_data.policy;
    //method = "PUT";
    //url_path = "/pool/" + edit_pool_data.pool_name + "/buckets";
    //body = compose_create_bucket_dict(csrf_token, key, policy);
    const tt = triple();
    method = tt.method;
    url_path = tt.url_path;
    body = tt.body;
  }
  else if (op == 3 || op == 4 || op == 5) {
    var accessKeyID;
    if (op == 3) {
      accessKeyID = edit_pool_data.accessKeyIDrw;
    }
    else if (op == 4) {
      accessKeyID = edit_pool_data.accessKeyIDro;
    }
    else if (op == 5) {
      accessKeyID = edit_pool_data.accessKeyIDwo;
    }

    method = "PUT";
    url_path = "/pool/" + edit_pool_data.pool_name + "/accessKeys";
    body = compose_access_key_update_dict(csrf_token, accessKeyID);
  }

  console.log("method: " + method);
  console.log("url_path: " + url_path);
  console.log("body: " + body);
  var request_options = {
    method: method,
    body: body,
  };

  fetch(url_path, request_options)
    .then(function(response) {
      if (!response.ok) {
        return response.json().then(
            function(data) {
              console.log("response-data: " + data);
              show_message(edit_pool_data.submit_button_name + " pool ... error: " + JSON.stringify(data));
              render_jsondata(data)
              if (data["pool_list"] != null) {
                edit_pool_data.mode = data["pool_list"][0]["minio_state"];
              }
              edit_pool_data.submit_button_disabled = false;
              edit_pool_data.submit_button_visible = true;
              throw new Error(JSON.stringify(data));
            })
      } else {
        return response.json().then(function(data) {
          show_message(edit_pool_data.submit_button_name + " pool ... done: " + JSON.stringify(data));
          render_jsondata(data)
          edit_pool_data.mode = data["pool_list"][0]["minio_state"]
          // update succeeded. do not re-enable button now.
        })
      }
    })
    .catch(function(err) {
      console.log("Fetch Error: ", err);
    });
}

const policies = ["none", "public", "upload", "download"];

const policyNames = ["readwrite", "readonly", "writeonly"];

//function stringify_dict(dict, csrf_token) {
//  dict["CSRF-Token"] = csrf_token;
//  return JSON.stringify(dict);
//}

function build_pool_desc() {
  var pooldesc = {};
  var buckets = new Array();
  var direct_hostnames = new Array();
  for (var i = 0; i < policies.length; i++) {
    buckets = push_buckets(buckets, edit_pool_data.buckets[i], policies[i]);
  }
  direct_hostnames = push_direct_hostnames(direct_hostnames,
                                          edit_pool_data.directHostnameDomains,
                                          edit_pool_data.direct_hostnames);
  pooldesc["owner_gid"] = edit_pool_data.group;
  pooldesc["buckets_directory"] = edit_pool_data.buckets_directory;
  pooldesc["buckets"] = buckets;
  // A dummy entry.
  pooldesc["access_keys"] = [{"policy_name": "readwrite"}, {"policy_name": "readonly"}, {"policy_name": "writeonly"}];
  pooldesc["direct_hostnames"] = direct_hostnames;
  pooldesc["expiration_date"] = parse_rfc3339(edit_pool_data.expiration_date);
  pooldesc["permit_status"] = edit_pool_data.permit_status;
  pooldesc["online_status"] = edit_pool_data.online_status;
  // Do not include "minio_state" nor "atime".
  return pooldesc;
}

function compose_create_dict(csrf_token) {
  var pooldesc = build_pool_desc();
  var dict = {"pool": pooldesc};
  //return stringify_dict(dict, csrf_token);
  dict["CSRF-Token"] = csrf_token;
  body = JSON.stringify(dict);
  return body;
}

function compose_update_dict(csrf_token) {
  var pooldesc = build_pool_desc();
  pooldesc["access_keys"] = edit_pool_data.accessKeys; // overwrite a dummy entry
  var dict = {"pool": pooldesc};
  //return stringify_dict(dict, csrf_token);
  dict["CSRF-Token"] = csrf_token;
  body = JSON.stringify(dict);
  return body;
}

function compose_create_bucket_dict(csrf_token, key, policy) {
  if (policy != "none" && policy != "upload" && policy != "download") {
    throw new Error("error: invalid policy: " + policy);
  }
  var pooldesc = {"buckets": [{"key": key, "policy": policy}]};
  var dict = {"pool": pooldesc};
  //return stringify_dict(dict, csrf_token);
  dict["CSRF-Token"] = csrf_token;
  body = JSON.stringify(dict);
  return body;
}

function compose_access_key_update_dict(csrf_token, accessKeyID) {
  var pooldesc = {"access_keys": [{"access_key": accessKeyID}]};
  var dict = {"pool": pooldesc};
  //return stringify_dict(dict, csrf_token);
  dict["CSRF-Token"] = csrf_token;
  body = JSON.stringify(dict);
  return body;
}

function compose_delete_dict(csrf_token) {
  var dict = {};
  //return stringify_dict(dict, csrf_token);
  dict["CSRF-Token"] = csrf_token;
  body = JSON.stringify(dict);
  return body;
}

function push_buckets(buckets, bucketList, policy) {
  var xs = bucketList.split(' ');
  for (var i = 0; i < xs.length; i++) {
    var bucket = xs[i];
    if (bucket != "") {
      var v = {"key": bucket, "policy": policy};
      buckets.push(v);
    }
  }
  return buckets;
}

function push_direct_hostnames(direct_hostnames, directHostnameDomains, hosts) {
  var xs = hosts.split(' ');
  for (var i = 0; i < xs.length; i++) {
    var directHostname = xs[i];
    if (directHostname != "") {
      if (!directHostname.endsWith("." + directHostnameDomains[0])) {
        directHostname += "." + directHostnameDomains[0];
      }
      direct_hostnames.push(directHostname);
    }
  }
  return direct_hostnames;
}

function run_debug() {
  var post_data = compose_create_dict(csrf_token);
  var put_data = compose_update_dict(csrf_token);
  var bkt_data = compose_create_bucket_dict(csrf_token);
  var key_data = compose_access_key_update_dict(csrf_token);
  var delete_data = compose_delete_dict(csrf_token);
  console.log("post_data: " + post_data);
  console.log("put_data: " + put_data);
  console.log("bkt_data: " + bkt_data);
  console.log("key_data: " + key_data);
  console.log("delete_data: " + delete_data);
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
  var s = "2022-03-31T00:00:00.000Z";
  var t = parse_rfc3339(s);
  var u = format_rfc3339(t);
  console.log("parse: " + s + " => " + t);
  console.log("unparse: " + t + " => " + u);
}

function get_pool_list() {
  show_message("get pool list ...");
  clear_status_field();
  const method = "GET";
  const url_path = "/pool";
  const request_options = {
    method: method,
    headers: {},
  };
  fetch(url_path, request_options)
    .then(function(response) {
      if (!response.ok) {
        return response.json().then(
          function(data) {
            show_message("get pool list ... error: " + JSON.stringify(data));
            render_jsondata(data)
            throw new Error(JSON.stringify(data));
          })
      }
      response.json().then(function(data) {
        csrf_token = data["CSRF-Token"];
        parse_pool_desc_list(data["pool_list"]);
        show_message("get pool list ... done");
      })
    })
    .catch(function(err) {
      console.log("Fetch Error: ", err);
    });
}

function get_template() {
  edit_pool_data.submit_button_disabled = true;
  show_message("get new pool ...");
  clear_status_field();
  const method = "GET";
  const url_path = "/template";
  const request_options = {
    method: method,
    headers: {},
  };
  fetch(url_path, request_options)
    .then(function(response) {
      if (!response.ok) {
        return response.json().then(
          function(data) {
            show_message("get new pool ... error: " + JSON.stringify(data));
            render_jsondata(data)
            // fatal error. do not re-enable the button. enable_update_button();
            throw new Error(JSON.stringify(data));
          })
      }
      response.json().then(function(data) {
        csrf_token = data["CSRF-Token"];
        get_template_body(data["pool_list"]);
        show_message("get new pool ... done");
        edit_pool_data.submit_button_disabled = false;
        edit_pool_data.submit_button_visible = true;
      })
    })
    .catch(function(err) {
      console.log("Fetch Error: ", err);
    });
}

function get_template_body(pool_desc_list) {
  pooldesc = pool_desc_list[0];
  copy_pool_desc_for_edit(pooldesc);
  edit_pool_data.submit_button_name = "Create";
  edit_pool_data.submit_button_disabled = false;
  edit_pool_data.submit_button_visible = true;
  edit_pool_data.pool_name_visible = true;
  edit_pool_data.buckets_directory_disabled = false;
  edit_pool_data.edit_pool_visible = false;
  list_pools_data.pool_data_visible = false;
}

function disable_create_button() {
  edit_pool_data.submit_button_disabled = true;
}

function enable_create_button() {
  edit_pool_data.submit_button_disabled = false;
}

function set_create_button_visibility(v) {
  edit_pool_data.submit_button_visible = v;
}

function disable_delete_button() {
  edit_pool_data.deleteButtonDisabled = true;
}

function enable_delete_button() {
  edit_pool_data.deleteButtonDisabled = false;
}

function perform_delete_pool(pooldesc) {
  disable_delete_button();
  show_message("delete pool ...");
  clear_status_field();
  var pool_name = pooldesc["pool_name"];
  console.log(`pool_name = ${pool_name}`);
  const request_options = {
    method: "DELETE",
    body: compose_delete_dict(csrf_token),
  };
  var url_path = "/pool/" + pool_name;
  fetch(url_path, request_options)
    .then(function(response) {
      if (!response.ok) {
        return response.json().then(
          function(data) {
            show_message("delete pool ... error: " + JSON.stringify(data));
            render_jsondata(data)
            enable_delete_button();
            throw new Error(JSON.stringify(data));
          })
      }
      response.json().then(function(data) {
        show_message("delete pool ... done");
        enable_delete_button();
        get_pool_list();
      })
    })
    .catch(function(err) {
      console.log("Fetch Error: ", err);
    });
}

function parse_pool_desc_list(pool_desc_list) {
  var div = "";
  var res = new Array();
  var items_list = new Array();
  edit_pool_data.pool_name_visible = false;
  edit_pool_data.edit_pool_visible = false;
  for (var k = 0; k < pool_desc_list.length; k++) {
    var pooldesc = pool_desc_list[k];
    var i = "<input v-on:click='kick_edit_pool(" + k + ")' type='button' class='button' value='Edit' />" +
        "<input v-on:click='kick_delete_pool(" + k + ")' type='button' class='button' value='Delete' :disabled='edit_pool_data.deleteButtonDisabled' />" +
        "<ul style='list-style: none;'>" +
        "<li v-for='item in items_list[" + k + "]'>" +
        "<span class='label'> {{ item.text.label }}: </span>" +
        " {{ item.text.value }} " +
        "</li>" +
        "</ul>" +
        "<hr>";
    res.push(i);
    items_list.push(pool_to_ul_text(pooldesc));
  }
  var div = "<div id='pool_list_viewer' v-if='pool_data_visible'>" +
      res.join("") +
      "</div>";
  var el = document.getElementById("pool_list")
  el.innerHTML = "";
  el.insertAdjacentHTML("beforeend", div);

  list_pools_data = {
    pool_data_visible: false,
    items_list: items_list,
    list_of_pools: pool_desc_list,
  };

  function run_edit_pool(i) {
    copy_pool_desc_for_edit(list_pools_data.list_of_pools[i]);
    edit_pool_data.pool_name_visible = true;
    edit_pool_data.buckets_directory_disabled = true;
    edit_pool_data.edit_pool_visible = true;
    list_pools_data.pool_data_visible = false;
    edit_pool_data.submit_button_name = "Update";
    edit_pool_data.submit_button_disabled = false;
    edit_pool_data.submit_button_visible = true;
  }

  function run_delete_pool(i) {
    perform_delete_pool(list_pools_data.list_of_pools[i])
  }

  list_pools_app = new Vue({
    el: "#pool_list_viewer",
    data: list_pools_data,
    methods: {
      kick_edit_pool: run_edit_pool,
      kick_delete_pool: run_delete_pool,
    }
  });

  list_pools_app.$mount();
  list_pools_data.list_of_pools = pool_desc_list;
  list_pools_data.pool_data_visible = true;
}

function pool_to_ul_text(pooldesc) {
  var buckets = pooldesc["buckets"];
  var accessKeys = pooldesc["access_keys"];
  var rwkey = chooseAccessKey(accessKeys, "readwrite");
  var rokey = chooseAccessKey(accessKeys, "readonly");
  var wokey = chooseAccessKey(accessKeys, "writeonly");

  return [
    {text: {label: "Buckets directory", value: pooldesc["buckets_directory"]}},
    {text: {label: "Unix user", value: pooldesc["owner_uid"]}},
    {text: {label: "Unix group", value: pooldesc["owner_gid"]}},
    {text: {label: "Private buckets", value: scan_buckets(buckets, "none")}},
    {text: {label: "Public buckets", value: scan_buckets(buckets, "public")}},
    {text: {label: "Public download buckets", value: scan_buckets(buckets, "download")}},
    {text: {label: "Public upload buckets", value: scan_buckets(buckets, "upload")}},
    {text: {label: "Access key ID (RW)", value: rwkey["access_key"]}},
    {text: {label: "Secret access key", value: rwkey["secret_key"]}},
    {text: {label: "Access key ID (RO)", value: rokey["access_key"]}},
    {text: {label: "Secret access key", value: rokey["secret_key"]}},
    {text: {label: "Access key ID (WO)", value: wokey["access_key"]}},
    {text: {label: "Secret access key", value: wokey["secret_key"]}},
    {text: {label: "Endpoint-URL", value: pooldesc["endpoint_url"]}},
    {text: {label: "Pool-ID", value: pooldesc["pool_name"]}},
    {text: {label: "Direct hostname", value: pooldesc["direct_hostnames"].join(' ')}},
    {text: {label: "MinIO state", value: pooldesc["minio_state"]}},
    {text: {label: "Expiration date", value: format_rfc3339_if_not_zero(pooldesc["expiration_date"])}},
    {text: {label: "Permitted", value: pooldesc["permit_status"]}},
    {text: {label: "Enabled", value: pooldesc["online_status"]}},
    {text: {label: "Last access time", value: format_rfc3339_if_not_zero(pooldesc["atime"])}},
  ];
}

function copy_pool_desc_for_edit(pooldesc) {
  var accessKeys = pooldesc["access_keys"];
  var rwkey = chooseAccessKey(accessKeys, "readwrite");
  var rokey = chooseAccessKey(accessKeys, "readonly");
  var wokey = chooseAccessKey(accessKeys, "writeonly");

  edit_pool_data.pool_name = pooldesc["pool_name"];
  edit_pool_data.user = pooldesc["owner_uid"];
  edit_pool_data.group = pooldesc["owner_gid"];
  edit_pool_data.buckets_directory = pooldesc["buckets_directory"];
  var buckets = pooldesc["buckets"];
  for (var i = 0; i < policies.length; i++) {
    edit_pool_data.buckets[i] = scan_buckets(buckets, policies[i]);
  }

  edit_pool_data.accessKeys = accessKeys;
  edit_pool_data.accessKeyIDrw = rwkey["access_key"];
  edit_pool_data.accessKeyIDro = rokey["access_key"];
  edit_pool_data.accessKeyIDwo = wokey["access_key"];
  edit_pool_data.secretAccessKeyrw = rwkey["secret_key"];
  edit_pool_data.secretAccessKeyro = rokey["secret_key"];
  edit_pool_data.secretAccessKeywo = wokey["secret_key"];

  edit_pool_data.key = "";           // for bucket creation
  edit_pool_data.policy = "";        // ditto.

  edit_pool_data.direct_hostnames = pooldesc["direct_hostnames"].join(' ');
  edit_pool_data.expiration_date = format_rfc3339_if_not_zero(pooldesc["expiration_date"]);
  edit_pool_data.permit_status = pooldesc["permit_status"];
  edit_pool_data.online_status = pooldesc["online_status"];
  edit_pool_data.mode = pooldesc["minio_state"];
  edit_pool_data.atime = format_rfc3339_if_not_zero(pooldesc["atime"]);
  edit_pool_data.groups = pooldesc["groups"];
  edit_pool_data.directHostnameDomains = pooldesc["directHostnameDomains"];
  edit_pool_data.facadeHostname = pooldesc["facadeHostname"];
  edit_pool_data.endpointURLs = pooldesc["endpoint_url"];
  show_message("editing");
}

function show_message(s) {
  show_status_data.message = "Message: " + s;
}

function clear_status_field() {
  render_jsondata({"status": "", "reason": "", "time": "0"})
}

function render_jsondata(data) {
  show_status(data["status"])
  show_reason(data["reason"])
  show_time(data["time"])
}

function show_status(s) {
  show_status_data.status = "Status: " + s;
}

function show_reason(s) {
  show_status_data.reason = "Reason: " + s;
}

function show_time(s) {
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

function chooseAccessKey(accessKeys, policyName) {
  for (var i = 0; i < accessKeys.length; i++) {
    var accessKey = accessKeys[i];
    if (accessKey["policy_name"] == policyName) {
      return accessKey;
    }
  }
  return undefined;
}

function scan_buckets(buckets, policy) {
  var res = new Array();
  for (var i = 0; i < buckets.length; i++) {
    var bucket = buckets[i];
    if (bucket["policy"] == policy) {
      res.push(bucket["key"]);
    }
  }
  return res.join(' ');
}
